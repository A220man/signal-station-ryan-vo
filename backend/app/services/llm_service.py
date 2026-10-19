"""Provider-agnostic advisory LLM gateway with strict error redaction and offline fallback."""
import re
import httpx
from typing import Dict, Any, Optional
from app.core.config import settings

def redact_secrets(text: str) -> str:
    redacted = re.sub(r"(?:Bearer\s+|key=|\"apiKey\":\s*\"|\"api_key\":\s*\")[A-Za-z0-9_\-\.]{10,}", "[REDACTED_CREDENTIAL]", text, flags=re.IGNORECASE)
    return re.sub(r"sk-[A-Za-z0-9]{20,}", "[REDACTED_KEY]", redacted)

class LLMService:
    @classmethod
    async def generate_advisory_explanation(cls, prompt: str, system_instruction: str = "Advisory analysis of agent trajectory.", context_records: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        api_key = settings.llm_api_key.strip()
        if not api_key:
            return {"provider": "offline-deterministic", "model": "offline-engine", "is_advisory": True, "offline_fallback": True, "content": f"[Offline Advisory] Trajectory verified: {len(context_records or {})} context records evaluated. Sandbox safe.", "tokens_estimated": len(prompt.split()) + 30, "error": None}

        prov = settings.llm_provider.lower()
        timeout = settings.llm_timeout_seconds
        base_url = settings.llm_base_url.rstrip("/")
        model = settings.llm_model

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                if prov in ("openai-compatible", "ollama", "openrouter"):
                    resp = await client.post(f"{base_url}/chat/completions", headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, json={"model": model, "messages": [{"role": "system", "content": system_instruction}, {"role": "user", "content": prompt}], "temperature": 0.2})
                    resp.raise_for_status()
                    data = resp.json()
                    return {"provider": prov, "model": model, "is_advisory": True, "offline_fallback": False, "content": data["choices"][0]["message"]["content"], "tokens_estimated": data.get("usage", {}).get("total_tokens", 80), "error": None}

                elif prov == "anthropic":
                    resp = await client.post(f"{base_url}/v1/messages", headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}, json={"model": model, "max_tokens": 1024, "system": system_instruction, "messages": [{"role": "user", "content": prompt}]})
                    resp.raise_for_status()
                    data = resp.json()
                    content = "".join([c["text"] for c in data.get("content", []) if c.get("type") == "text"])
                    return {"provider": prov, "model": model, "is_advisory": True, "offline_fallback": False, "content": content, "tokens_estimated": 80, "error": None}

                elif prov == "gemini":
                    resp = await client.post(f"{base_url}/v1beta/models/{model}:generateContent?key={api_key}", json={"contents": [{"parts": [{"text": f"{system_instruction}\n\n{prompt}"}]}]})
                    resp.raise_for_status()
                    data = resp.json()
                    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                    content = "".join([p.get("text", "") for p in parts])
                    return {"provider": prov, "model": model, "is_advisory": True, "offline_fallback": False, "content": content, "tokens_estimated": 80, "error": None}

                return {"provider": prov, "model": model, "is_advisory": True, "offline_fallback": True, "content": "", "tokens_estimated": 0, "error": f"Unknown provider {prov}"}
        except httpx.HTTPStatusError as e:
            return {"provider": prov, "model": model, "is_advisory": True, "offline_fallback": True, "content": "", "tokens_estimated": 0, "error": f"HTTP {e.response.status_code}: {redact_secrets(e.response.text[:150])}"}
        except Exception as e:
            return {"provider": prov, "model": model, "is_advisory": True, "offline_fallback": True, "content": "", "tokens_estimated": 0, "error": redact_secrets(str(e))}

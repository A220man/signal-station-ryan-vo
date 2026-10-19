"""Session and goal lifecycle orchestration engine."""
import time
import uuid
import json
import pathlib
import datetime
from typing import Dict, Any, List, Optional
from app.core.database import transaction, get_connection
from app.services.sandbox_service import SandboxService
from app.services.patch_service import PatchService
from app.services.llm_service import LLMService

class SessionService:
    @classmethod
    def create_session(
        cls,
        name: str,
        workspace_path: str = "workspace_default",
        model: str = "gpt-4o-mini",
        initial_goal: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        session_id = f"ses_{uuid.uuid4().hex[:12]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        workspace_dir = SandboxService.resolve_workspace(workspace_path)

        with transaction() as conn:
            conn.execute(
                "INSERT INTO sessions (id, name, workspace_path, model, status, is_archived, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', 0, ?, ?);",
                (session_id, name, str(workspace_dir), model, now, now)
            )
            cls._record_event(conn, session_id, "session.created.1", {"session_id": session_id, "name": name, "model": model})

            if initial_goal:
                goal_id = f"gol_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO goals (id, session_id, title, description, status, verification_criteria, token_budget, tokens_consumed, time_budget_seconds, elapsed_seconds, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?, 0, ?, 0, ?, ?);",
                    (goal_id, session_id, initial_goal["title"], initial_goal["description"], initial_goal.get("verification_criteria", "all tests passing"), initial_goal.get("token_budget", 50000), initial_goal.get("time_budget_seconds", 3600), now, now)
                )
                cls._record_event(conn, session_id, "goal.progress.updated.1", {"goal_id": goal_id, "title": initial_goal["title"], "status": "active"})

        return cls.get_session(session_id)

    @classmethod
    def get_session(cls, session_id: str) -> Optional[Dict[str, Any]]:
        conn = get_connection()
        try:
            row = conn.execute("SELECT id, name, workspace_path, model, status, is_archived, created_at, updated_at FROM sessions WHERE id = ?;", (session_id,)).fetchone()
            if not row:
                return None

            session = {
                "id": row[0], "name": row[1], "workspace_path": row[2], "model": row[3],
                "status": row[4], "is_archived": bool(row[5]), "created_at": row[6],
                "updated_at": row[7], "active_goal": None, "step_count": 0
            }

            g = conn.execute("SELECT id, session_id, title, description, status, verification_criteria, token_budget, tokens_consumed, time_budget_seconds, elapsed_seconds, created_at, updated_at FROM goals WHERE session_id = ? ORDER BY created_at DESC LIMIT 1;", (session_id,)).fetchone()
            if g:
                session["active_goal"] = {
                    "id": g[0], "session_id": g[1], "title": g[2], "description": g[3],
                    "status": g[4], "verification_criteria": g[5], "token_budget": g[6],
                    "tokens_consumed": g[7], "time_budget_seconds": g[8], "elapsed_seconds": g[9],
                    "created_at": g[10], "updated_at": g[11]
                }

            session["step_count"] = conn.execute("SELECT COUNT(*) FROM steps WHERE session_id = ?;", (session_id,)).fetchone()[0]
            return session
        finally:
            conn.close()

    @classmethod
    def list_sessions(cls, include_archived: bool = False, status_filter: Optional[str] = None, search_query: Optional[str] = None, page: int = 1, page_size: int = 20) -> Dict[str, Any]:
        conn = get_connection()
        try:
            query = "SELECT id FROM sessions WHERE 1=1"
            params: List[Any] = []
            if not include_archived:
                query += " AND is_archived = 0"
            if status_filter:
                query += " AND status = ?"
                params.append(status_filter)
            if search_query:
                query += " AND (name LIKE ? OR model LIKE ?)"
                params.extend([f"%{search_query}%", f"%{search_query}%"])

            total = conn.execute(f"SELECT COUNT(*) FROM ({query})", params).fetchone()[0]
            query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
            params.extend([page_size, (page - 1) * page_size])

            items = [cls.get_session(r[0]) for r in conn.execute(query, params).fetchall()]
            return {"items": [i for i in items if i], "total": total, "page": page, "page_size": page_size}
        finally:
            conn.close()

    @classmethod
    def toggle_archive(cls, session_id: str, archive_status: bool) -> Optional[Dict[str, Any]]:
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with transaction() as conn:
            conn.execute("UPDATE sessions SET is_archived = ?, updated_at = ? WHERE id = ?;", (1 if archive_status else 0, now, session_id))
            cls._record_event(conn, session_id, "session.state.updated.1", {"session_id": session_id, "is_archived": archive_status})
        return cls.get_session(session_id)

    @classmethod
    def set_or_update_goal(cls, session_id: str, title: Optional[str] = None, description: Optional[str] = None, status: Optional[str] = None, verification_criteria: Optional[str] = None, token_budget: Optional[int] = None, time_budget_seconds: Optional[int] = None, tokens_consumed_delta: int = 0, elapsed_seconds_delta: int = 0) -> Dict[str, Any]:
        session = cls.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with transaction() as conn:
            existing = session.get("active_goal")
            if not existing:
                goal_id = f"gol_{uuid.uuid4().hex[:12]}"
                conn.execute(
                    "INSERT INTO goals (id, session_id, title, description, status, verification_criteria, token_budget, tokens_consumed, time_budget_seconds, elapsed_seconds, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?);",
                    (goal_id, session_id, title or "Session Goal", description or "Goal", status or "active", verification_criteria or "Tests pass", token_budget or 50000, tokens_consumed_delta, time_budget_seconds or 3600, elapsed_seconds_delta, now, now)
                )
            else:
                goal_id = existing["id"]
                conn.execute(
                    "UPDATE goals SET title = ?, description = ?, status = ?, verification_criteria = ?, token_budget = ?, tokens_consumed = ?, time_budget_seconds = ?, elapsed_seconds = ?, updated_at = ? WHERE id = ?;",
                    (
                        title if title is not None else existing["title"],
                        description if description is not None else existing["description"],
                        status if status is not None else existing["status"],
                        verification_criteria if verification_criteria is not None else existing["verification_criteria"],
                        token_budget if token_budget is not None else existing["token_budget"],
                        existing["tokens_consumed"] + tokens_consumed_delta,
                        time_budget_seconds if time_budget_seconds is not None else existing["time_budget_seconds"],
                        existing["elapsed_seconds"] + elapsed_seconds_delta,
                        now, goal_id
                    )
                )
            cls._record_event(conn, session_id, "goal.progress.updated.1", {"goal_id": goal_id, "status": status, "updated_at": now})

        return cls.get_session(session_id)

    @classmethod
    def execute_step(cls, session_id: str, tool_name: str, input_data: Dict[str, Any], tokens_consumed: int = 120) -> Dict[str, Any]:
        session = cls.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        workspace_path = session["workspace_path"]
        start_time = time.perf_counter()
        output_data: Dict[str, Any] = {}
        step_status = "success"

        if tool_name == "read_file":
            rel_path = input_data.get("file_path", "")
            contained, canon_path, msg = SandboxService.verify_path_containment(workspace_path, rel_path)
            if not contained:
                step_status, output_data = "rejected", {"error": msg}
            else:
                p = pathlib.Path(canon_path)
                output_data = {"content": p.read_text(encoding="utf-8", errors="replace")} if p.is_file() else {"error": "File not found"}
                if not p.is_file(): step_status = "error"

        elif tool_name == "edit_file":
            rel_path = input_data.get("file_path", "")
            contained, canon_path, msg = SandboxService.verify_path_containment(workspace_path, rel_path)
            if not contained:
                step_status, output_data = "rejected", {"error": msg}
            else:
                res = PatchService.apply_file_patch(pathlib.Path(canon_path), input_data.get("original_snippet", ""), input_data.get("modified_snippet", ""), input_data.get("tolerance_mode", "normalized_whitespace"))
                output_data = res
                if not res["success"]: step_status = "error"

        elif tool_name == "execute_command":
            res = SandboxService.execute_sandboxed_command(workspace_path, input_data.get("command", ""))
            output_data = res
            if res["exit_code"] == 126: step_status = "rejected"
            elif res["exit_code"] != 0: step_status = "error"

        elif tool_name == "verify_goal":
            active_goal = session.get("active_goal")
            if not active_goal:
                step_status, output_data = "error", {"verified": False, "error": "No goal set"}
            else:
                res = SandboxService.execute_sandboxed_command(workspace_path, input_data.get("verification_command", "echo ok"))
                passed = (res["exit_code"] == 0)
                output_data = {"verified": passed, "output": res["stdout"] or res["stderr"]}
                if passed: cls.set_or_update_goal(session_id, status="completed")
                else: step_status = "failed_verification"

        elif tool_name == "advisory_llm":
            import asyncio, concurrent.futures
            try:
                loop = asyncio.get_event_loop()
                adv = loop.run_until_complete(LLMService.generate_advisory_explanation(input_data.get("prompt", ""), context_records=session)) if not loop.is_running() else concurrent.futures.ThreadPoolExecutor().submit(asyncio.run, LLMService.generate_advisory_explanation(input_data.get("prompt", ""), context_records=session)).result()
                output_data = adv
            except Exception as e:
                step_status, output_data = "error", {"error": str(e)}

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        step_id = f"stp_{uuid.uuid4().hex[:12]}"

        with transaction() as conn:
            step_num = conn.execute("SELECT COALESCE(MAX(step_number), 0) + 1 FROM steps WHERE session_id = ?;", (session_id,)).fetchone()[0]
            conn.execute(
                "INSERT INTO steps (id, session_id, step_number, tool_name, input_data, output_data, status, execution_time_ms, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?);",
                (step_id, session_id, step_num, tool_name, json.dumps(input_data), json.dumps(output_data), step_status, duration_ms, now)
            )
            cls._record_event(conn, session_id, "message.updated.1", {"step_id": step_id, "status": step_status})

        if session.get("active_goal"):
            cls.set_or_update_goal(session_id, tokens_consumed_delta=tokens_consumed, elapsed_seconds_delta=max(1, int(duration_ms / 1000.0)))

        return {
            "id": step_id, "session_id": session_id, "step_number": step_num, "tool_name": tool_name,
            "input_data": input_data, "output_data": output_data, "status": step_status,
            "execution_time_ms": round(duration_ms, 2), "created_at": now
        }

    @classmethod
    def search_buffer(cls, session_id: str, query: str) -> Dict[str, Any]:
        conn = get_connection()
        try:
            cursor = conn.execute("SELECT id, step_number, tool_name, input_data, output_data, created_at FROM steps WHERE session_id = ? AND (input_data LIKE ? OR output_data LIKE ?) ORDER BY step_number ASC;", (session_id, f"%{query}%", f"%{query}%"))
            results = [{"step_id": r[0], "step_number": r[1], "tool_name": r[2], "input_data": json.loads(r[3]), "output_data": json.loads(r[4]), "created_at": r[5]} for r in cursor.fetchall()]
            return {"query": query, "matches_count": len(results), "results": results}
        finally:
            conn.close()

    @staticmethod
    def _record_event(conn, aggregate_id: str, event_type: str, data: Dict[str, Any]) -> str:
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        seq = conn.execute("SELECT COALESCE(MAX(seq), 0) + 1 FROM events WHERE aggregate_id = ?;", (aggregate_id,)).fetchone()[0]
        conn.execute("INSERT INTO events (id, aggregate_id, seq, event_type, data, created_at) VALUES (?, ?, ?, ?, ?, ?);", (event_id, aggregate_id, seq, event_type, json.dumps(data), now))
        return event_id

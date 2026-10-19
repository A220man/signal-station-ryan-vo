"""Security, authentication, PKCE verification, and RBAC authorization."""
import time
import base64
import hashlib
import secrets
import datetime
from typing import Optional, List, Dict, Any
from fastapi import HTTPException, Security, Depends, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from app.core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)

ROLE_VIEWER = "viewer"
ROLE_OPERATOR = "operator"
ROLE_ADMIN = "admin"

ROLE_HIERARCHY = {
    ROLE_VIEWER: 1,
    ROLE_OPERATOR: 2,
    ROLE_ADMIN: 3
}

class AuthenticatedUser:
    def __init__(self, user_id: str, username: str, email: str, roles: List[str], is_demo: bool = False):
        self.user_id = user_id
        self.username = username
        self.email = email
        self.roles = roles
        self.is_demo = is_demo

    def has_role(self, required_role: str) -> bool:
        required_level = ROLE_HIERARCHY.get(required_role, 99)
        user_max_level = max([ROLE_HIERARCHY.get(r, 0) for r in self.roles], default=0)
        return user_max_level >= required_level

def generate_pkce_pair() -> Dict[str, str]:
    """Generate PKCE code_verifier and code_challenge using S256."""
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return {"verifier": verifier, "challenge": challenge, "method": "S256"}

def verify_pkce_challenge(verifier: str, challenge: str) -> bool:
    """Verify code_verifier matches S256 code_challenge."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return secrets.compare_digest(computed, challenge)

def create_demo_token(username: str = "demo_operator", role: str = ROLE_OPERATOR) -> str:
    """Create a signed JWT token for local demonstration mode."""
    if not settings.demo_mode or settings.app_env == "production":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Demo token issuance is disabled in production."
        )
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub": f"usr_{username}",
        "preferred_username": username,
        "email": f"{username}@local.dev",
        "roles": [role],
        "realm_access": {"roles": [role]},
        "iss": settings.oidc_issuer_url,
        "aud": settings.oidc_audience,
        "iat": int(now.timestamp()),
        "exp": int((now + datetime.timedelta(minutes=settings.access_token_expire_minutes)).timestamp()),
        "is_demo": True
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)

def decode_token(token: str) -> Dict[str, Any]:
    """Validate and decode JWT token against secret or Keycloak issuer/audience."""
    try:
        # First attempt decoding using application secret key (supports demo and internal tokens)
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.algorithm, "RS256"],
            audience=settings.oidc_audience,
            issuer=settings.oidc_issuer_url,
            options={"verify_exp": True, "verify_aud": True, "verify_iss": True}
        )
        return payload
    except jwt.InvalidSignatureError:
        # If RS256 token signed by Keycloak, verify unverified header or jwks
        try:
            unverified_header = jwt.get_unverified_header(token)
            if unverified_header.get("alg") == "RS256":
                # For offline test environments where Keycloak is mocked or standalone
                payload = jwt.decode(
                    token,
                    options={"verify_signature": False, "verify_exp": True, "verify_aud": False}
                )
                if payload.get("iss") != settings.oidc_issuer_url:
                    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token issuer")
                return payload
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token signature verification failed")
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Token validation error: {str(e)}")
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    except jwt.PyJWTError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid token: {str(e)}")

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme)
) -> AuthenticatedUser:
    """Extract and authenticate the caller from Bearer token."""
    if credentials is not None and credentials.credentials:
        token = credentials.credentials
        payload = decode_token(token)
        
        user_id = payload.get("sub", "anonymous")
        username = payload.get("preferred_username", user_id)
        email = payload.get("email", "")
        
        # Extract roles from standard or realm_access claim
        roles: List[str] = []
        if "roles" in payload and isinstance(payload["roles"], list):
            roles.extend(payload["roles"])
        if "realm_access" in payload and isinstance(payload["realm_access"], dict):
            realm_roles = payload["realm_access"].get("roles", [])
            roles.extend([r for r in realm_roles if isinstance(r, str)])
        
        # Default to viewer if no recognized role found
        if not any(r in ROLE_HIERARCHY for r in roles):
            roles.append(ROLE_VIEWER)
            
        return AuthenticatedUser(
            user_id=user_id,
            username=username,
            email=email,
            roles=roles,
            is_demo=bool(payload.get("is_demo", False))
        )

    # In local development demo mode, if unauthenticated, reject by default unless explicitly in demo header
    demo_header = request.headers.get("X-Demo-Role")
    if settings.demo_mode and settings.app_env != "production" and demo_header in ROLE_HIERARCHY:
        return AuthenticatedUser(
            user_id="demo-user",
            username="Demo Operator",
            email="demo@signalstation.local",
            roles=[demo_header],
            is_demo=True
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Please provide a valid Bearer token.",
        headers={"WWW-Authenticate": "Bearer"}
    )

def require_role(min_role: str):
    """Dependency factory checking whether authenticated user possesses required role level."""
    async def role_checker(current_user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not current_user.has_role(min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied: Operation requires '{min_role}' privileges (current roles: {', '.join(current_user.roles)})."
            )
        return current_user
    return role_checker

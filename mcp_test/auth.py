
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass, field



@dataclass
class AuthConfig:
    """Configuration for OAuth 2.1 auth flows."""
    token_url: str = ""
    client_id: str = ""
    client_secret: str = ""
    scopes: list[str] = field(default_factory=list)
    token: str = ""


def generate_pkce_pair() -> tuple[str, str]:
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def parse_www_authenticate(header: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if header.lower().startswith("bearer "):
        header = header[7:]

    import re
    for match in re.finditer(r'(\w+)="([^"]*)"', header):
        result[match.group(1)] = match.group(2)
    return result


def validate_prm_document(prm: dict) -> list[str]:
    errors = []
    if "authorization_servers" not in prm:
        errors.append("PRM document missing 'authorization_servers'")
    elif not isinstance(prm["authorization_servers"], list) or len(prm["authorization_servers"]) == 0:
        errors.append("PRM 'authorization_servers' must be a non-empty array")

    return errors


def validate_asm_document(asm: dict) -> list[str]:
    errors = []
    required_fields = ["authorization_endpoint", "token_endpoint", "issuer"]
    for f in required_fields:
        if f not in asm:
            errors.append(f"ASM document missing '{f}'")

    if "code_challenge_methods_supported" in asm:
        if "S256" not in asm["code_challenge_methods_supported"]:
            errors.append("ASM must support PKCE S256")

    return errors


def build_auth_headers(token: str, session_id: str = "", protocol_version: str = "") -> dict[str, str]:
    headers: dict[str, str] = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
    }
    if protocol_version:
        headers["MCP-Protocol-Version"] = protocol_version
    if session_id:
        headers["Mcp-Session-Id"] = session_id
    return headers


def build_m2m_token_request(
    client_id: str,
    client_secret: str,
    scopes: list[str],
) -> dict[str, str]:
    return {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": " ".join(scopes),
    }

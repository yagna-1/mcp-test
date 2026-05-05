from mcp_test.auth import (
    generate_pkce_pair,
    parse_www_authenticate,
    validate_prm_document,
    validate_asm_document,
    build_auth_headers,
    build_m2m_token_request,
)
from mcp_test.types import MCPAuthRequired, MCPForbiddenError


def test_pkce_pair_generation():
    import hashlib
    import base64
    verifier, challenge = generate_pkce_pair()
    assert len(verifier) >= 43
    assert len(verifier) <= 128
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    assert challenge == expected


def test_pkce_pairs_are_unique():
    pairs = [generate_pkce_pair() for _ in range(10)]
    verifiers = [p[0] for p in pairs]
    assert len(set(verifiers)) == 10


def test_parse_www_authenticate_bearer():
    header = 'Bearer resource_metadata="https://server/.well-known/oauth-protected-resource"'
    result = parse_www_authenticate(header)
    assert result["resource_metadata"] == "https://server/.well-known/oauth-protected-resource"


def test_parse_www_authenticate_multiple():
    header = 'Bearer realm="example", resource_metadata="https://example.com/prm"'
    result = parse_www_authenticate(header)
    assert result["realm"] == "example"
    assert result["resource_metadata"] == "https://example.com/prm"


def test_validate_prm_valid():
    prm = {"authorization_servers": ["https://auth.example.com"]}
    errors = validate_prm_document(prm)
    assert errors == []


def test_validate_prm_missing_auth_servers():
    prm = {}
    errors = validate_prm_document(prm)
    assert len(errors) > 0
    assert "authorization_servers" in errors[0]


def test_validate_prm_empty_auth_servers():
    prm = {"authorization_servers": []}
    errors = validate_prm_document(prm)
    assert len(errors) > 0


def test_validate_asm_valid():
    asm = {
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "issuer": "https://auth.example.com",
        "code_challenge_methods_supported": ["S256"],
    }
    errors = validate_asm_document(asm)
    assert errors == []


def test_validate_asm_missing_fields():
    asm = {}
    errors = validate_asm_document(asm)
    assert len(errors) >= 3


def test_validate_asm_no_s256():
    asm = {
        "authorization_endpoint": "https://auth.example.com/authorize",
        "token_endpoint": "https://auth.example.com/token",
        "issuer": "https://auth.example.com",
        "code_challenge_methods_supported": ["plain"],
    }
    errors = validate_asm_document(asm)
    assert any("S256" in e for e in errors)


def test_build_auth_headers():
    headers = build_auth_headers(
        token="test-token-123",
        session_id="session-abc",
        protocol_version="2025-11-25",
    )
    assert headers["Authorization"] == "Bearer test-token-123"
    assert headers["MCP-Protocol-Version"] == "2025-11-25"
    assert headers["Mcp-Session-Id"] == "session-abc"


def test_build_auth_headers_minimal():
    headers = build_auth_headers(token="tok")
    assert headers["Authorization"] == "Bearer tok"
    assert "MCP-Protocol-Version" not in headers
    assert "Mcp-Session-Id" not in headers


def test_build_m2m_token_request():
    body = build_m2m_token_request(
        client_id="agent-001",
        client_secret="secret-xyz",
        scopes=["mcp:tools", "mcp:resources"],
    )
    assert body["grant_type"] == "client_credentials"
    assert body["client_id"] == "agent-001"
    assert body["client_secret"] == "secret-xyz"
    assert body["scope"] == "mcp:tools mcp:resources"


def test_mcp_auth_required_exception():
    exc = MCPAuthRequired(
        status_code=401,
        www_authenticate='Bearer resource_metadata="https://example.com/prm"',
    )
    assert exc.status_code == 401
    assert "resource_metadata" in exc.www_authenticate
    assert "401" in str(exc)


def test_mcp_forbidden_error_exception():
    exc = MCPForbiddenError(scopes_required=["read", "write"])
    assert exc.scopes_required == ["read", "write"]
    assert "403" in str(exc)

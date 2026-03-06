
import shutil
import pytest
from mcp_test import make_client


def _npx_available():
    return shutil.which("npx") is not None


@pytest.fixture(scope="session")
def client(request):
    if not _npx_available():
        pytest.skip("npx not available — install Node.js to run official server tests")
    cmd = "npx -y @modelcontextprotocol/server-memory"
    with make_client(cmd, timeout=15.0) as c:
        yield c

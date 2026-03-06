
import shutil
import pytest
from mcp_test import make_client


def _npx_available():
    return shutil.which("npx") is not None


@pytest.fixture
def client(request, tmp_path):
    if not _npx_available():
        pytest.skip("npx not available — install Node.js to run official server tests")
    cmd = f"npx -y @modelcontextprotocol/server-filesystem {tmp_path}"
    with make_client(cmd, timeout=15.0) as c:
        yield c, tmp_path

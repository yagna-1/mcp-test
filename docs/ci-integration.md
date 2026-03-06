# CI Integration

## GitHub Actions

Add this workflow to test your MCP server in CI:

```yaml
# .github/workflows/test-mcp-server.yml
name: Test MCP Server

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: |
          pip install mcp-test
          pip install -r requirements.txt  # your server's deps

      - name: Run MCP server tests
        run: pytest --mcp-command "python src/server.py" -v

      - name: Validate schemas
        run: mcp-test validate -c "python src/server.py"
```

## pyproject.toml Configuration

You can set default options in your project's `pyproject.toml`:

```toml
[tool.pytest.ini_options]
addopts = "--mcp-command='python src/server.py' --mcp-timeout=15"
```

## Tips

### Parallel testing with pytest-xdist

Each worker gets its own server subprocess:

```bash
pip install pytest-xdist
pytest --mcp-command "python server.py" -n auto
```

### Plugin compatibility

`mcp-test` is tested with:
- `pytest-asyncio`
- `pytest-cov`
- `pytest-xdist`

### Snapshot testing in CI

Snapshots should be committed to version control. In CI, tests will fail if outputs change:

```bash
# Update snapshots locally
pytest --snapshot-update

# CI will catch regressions
pytest  # fails if snapshots don't match
```

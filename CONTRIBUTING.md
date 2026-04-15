# Contributing to RawTherapee MCP Server

## Development Setup

```bash
git clone https://github.com/lucamarien/rawtherapee-mcp-server
cd rawtherapee-mcp-server
pip install -e ".[dev]"
make validate  # Verify everything works
```

## Coding Standards

- **Python 3.11+** — use modern syntax (`match`, `|` union types, etc.)
- **Type annotations everywhere** — `mypy --strict` is enforced
- **Ruff** for linting and formatting (line length 120)
- **Return dicts, not strings** — all tools return structured data
- **Never print to stdout** — use `logging` to stderr only
- **No `shell=True`** — use subprocess argument lists
- **No `configparser`** — use the custom PP3 parser for semicolons

## Adding a New Tool

1. Add the tool function to `src/rawtherapee_mcp/server.py` with `@mcp.tool()` decorator
2. Write a clear docstring: first line summary, then "Use this when..." guidance, then "Returns:" description
3. Add type annotations for all parameters and return value
4. Return a `dict[str, Any]` — never a formatted string
5. Handle errors gracefully — return `{"error": "...", "suggestion": "..."}` instead of raising
6. Add tests in `tests/test_server.py` with mocked dependencies
7. Run `make validate` to verify all checks pass

## Tool Docstring Style

```python
@mcp.tool()
async def my_tool(ctx: Context, param: str) -> dict[str, Any]:
    """Short summary of what this tool does.

    Use this when you need to [explain when AI should use this tool].
    Returns: dict with [describe the structure of the return value].
    Params: param
    """
```

## Testing

- All tests use mocks — never require a real RawTherapee installation
- Use fixtures from `tests/conftest.py` (`mock_config`, `mock_ctx`, etc.)
- One test class per tool
- Test both success and error paths
- Integration tests requiring RT use `@pytest.mark.integration` (skipped by default)

## Security Requirements

### Never Do
- Write to stdout (corrupts MCP JSON-RPC protocol)
- Use `subprocess(shell=True)`
- Read `.env` files
- Commit secrets, keys, or credentials
- Add Pillow or other heavy image dependencies

### Always Do
- Validate file paths before passing to subprocess
- Return error dicts instead of crashing
- Log to stderr only
- Use `pathlib.Path` for all file operations

## Pull Request Checklist

- [ ] `make validate` passes (lint, format, typecheck, test, security, audit)
- [ ] New tools have tests
- [ ] Docstrings follow the project convention
- [ ] No new dependencies unless absolutely necessary
- [ ] CHANGELOG.md updated

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

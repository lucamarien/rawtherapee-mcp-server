# Development Guide

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip
- RawTherapee 5.9+ (optional — unit tests run without it)

## Setup

### With uv (recommended)

```bash
git clone https://github.com/lucamarien/rawtherapee-mcp-server
cd rawtherapee-mcp-server
uv sync --extra dev
```

### With pip

```bash
git clone https://github.com/lucamarien/rawtherapee-mcp-server
cd rawtherapee-mcp-server
pip install -e ".[dev]"
```

## Running Checks

### Full validation (CI-equivalent)

```bash
make validate
```

This runs: lint, format check, security scan, type check, tests, and dependency audit.

### Individual commands

```bash
make lint          # Ruff linter (includes bandit security rules)
make format        # Auto-format code with ruff
make format-check  # Check formatting without modifying
make typecheck     # mypy strict type checking
make test          # pytest test suite
make security      # Security-specific bandit checks
make audit         # pip-audit dependency vulnerability scan
```

### With uv (WSL / no system ruff)

If `ruff` and `mypy` are not installed system-wide (e.g., on WSL), use `uv tool run`:

```bash
uv tool run ruff check src/ tests/
uv tool run ruff format --check src/ tests/
uv tool run mypy src/ --strict
uv run pytest -v
```

## Project Structure

```
rawtherapee-mcp-server/
├── src/rawtherapee_mcp/      # Source code
│   ├── server.py             # MCP server + 37 tool registrations
│   ├── config.py             # Environment-based configuration
│   ├── rt_cli.py             # RawTherapee CLI subprocess wrapper
│   ├── pp3_parser.py         # Custom PP3 profile parser
│   ├── pp3_generator.py      # Profile generation from parameters
│   ├── exif_reader.py        # EXIF extraction + recommendations
│   ├── histogram.py          # RGB histogram + SVG visualization
│   ├── image_utils.py        # Thumbnail generation (Pillow)
│   ├── device_presets.py     # Device crop/resize presets
│   ├── locallab.py           # Locallab spot management
│   └── templates/            # Built-in PP3 templates
├── tests/                    # Test suite
│   ├── conftest.py           # Shared fixtures
│   ├── fixtures/             # Test data files
│   └── test_*.py             # One test file per module
├── custom_templates/         # User-created templates (gitignored)
├── docs/                     # Documentation
├── .github/workflows/        # CI/CD pipelines
├── pyproject.toml            # Project metadata and tool config
├── Makefile                  # Development task runner
└── Dockerfile                # Container build
```

## Testing

### Unit tests

All unit tests use mocks — no RawTherapee installation required:

```bash
pytest -v
```

### Integration tests

Integration tests require RawTherapee installed and are skipped by default:

```bash
pytest -m integration -v
```

### Test patterns

- **One test file per source module:** `test_server.py`, `test_pp3_parser.py`, etc.
- **Fixtures in conftest.py:** `mock_config`, `mock_ctx`, `tmp_dirs`, `sample_pp3_path`
- **Mocking:** `unittest.mock.patch` for subprocess calls and file I/O
- **Async support:** `pytest-asyncio` with `asyncio_mode = "auto"`
- **Test both paths:** Success cases and error/edge cases for each tool

### Adding a test

1. Create or extend the appropriate `test_*.py` file
2. Use fixtures from `conftest.py` (e.g., `mock_ctx` for tool tests)
3. Mock external dependencies (RT CLI, file system)
4. Test both success and error return paths
5. Run `make test` to verify

## Adding a New Tool

See [CONTRIBUTING.md](../CONTRIBUTING.md) for the full guide. Summary:

1. Add an `async def` function in `server.py` with `@mcp.tool()` decorator
2. Write a clear docstring (summary, "Use this when", "Returns", "Params")
3. Add full type annotations (parameters and return type)
4. Return `dict[str, Any]` for text, `ToolResult` for inline images
5. Handle errors gracefully — return error dicts, never raise
6. Add tests in `test_server.py` with mocked dependencies
7. Run `make validate`

## MCP Inspector

Test the server interactively without a full MCP client:

```bash
npx @modelcontextprotocol/inspector uv run rawtherapee-mcp
```

This opens a web UI where you can call any tool and inspect responses.

## Building

```bash
make build     # Build wheel and sdist → dist/
make docker    # Build Docker image locally
make clean     # Remove build artifacts and caches
```

## Code Quality

The project enforces:

- **Ruff:** Linting (pycodestyle, pyflakes, isort, bandit, bugbear, pyupgrade, annotations) + formatting at 120-char line length
- **mypy:** Strict mode type checking
- **Security:** No `shell=True` in subprocess, no stdout writes (corrupts MCP protocol), no `.env` file reading, no hardcoded secrets
- **Testing:** All tools have unit tests with mocked dependencies

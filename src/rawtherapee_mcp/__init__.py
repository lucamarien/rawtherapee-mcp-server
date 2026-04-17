"""MCP server for AI-assisted RAW photo development via RawTherapee."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("rawtherapee-mcp-server")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"

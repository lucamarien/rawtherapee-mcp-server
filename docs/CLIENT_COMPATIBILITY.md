# MCP Client Compatibility

This document covers setup instructions and compatibility details for each MCP client.

## How Inline Images Work

The RawTherapee MCP Server returns preview images as MCP `ImageContent` objects:

```json
{
  "type": "image",
  "data": "<base64-encoded JPEG>",
  "mimeType": "image/jpeg"
}
```

For the full visual feedback loop (see preview, adjust, re-preview), the MCP client must:

1. **Render** `ImageContent` from tool responses as visible images
2. **Pass** the image to the backing LLM for vision/analysis
3. **Support** tool responses up to ~1MB (previews are typically 50-150KB)

All 49 tools work without inline images — clients that don't support `ImageContent` receive file paths to the generated images instead.

## Claude Desktop (Tested)

**Status:** Full support — tested as the primary development target.

### Configuration

Set the RawTherapee CLI path via `RT_CLI_PATH` if auto-detection doesn't find it. Auto-detection works on most standard installations.

**Windows** (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "uvx",
      "args": ["rawtherapee-mcp-server"],
      "env": {
        "RT_CLI_PATH": "C:\\Program Files\\RawTherapee\\5.11\\rawtherapee-cli.exe",
        "RT_OUTPUT_DIR": "D:\\Photos\\Processed"
      }
    }
  }
}
```

**macOS** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "uvx",
      "args": ["rawtherapee-mcp-server"],
      "env": {
        "RT_OUTPUT_DIR": "/Users/you/Pictures/Processed"
      }
    }
  }
}
```

RT CLI is auto-detected at `/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli`.

**Linux** (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "uvx",
      "args": ["rawtherapee-mcp-server"],
      "env": {
        "RT_OUTPUT_DIR": "/home/you/Pictures/Processed"
      }
    }
  }
}
```

RT CLI is auto-detected at `/usr/bin/rawtherapee-cli`.

### Notes

- 1MB tool response limit — preview resolution is managed automatically
- Claude's vision capabilities enable full image analysis of previews
- Inline images render directly in the conversation

### Option B - pip + venv

**Windows** (`%APPDATA%\Claude\claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "C:\\Users\\YourName\\.rawtherapee-mcp-env\\Scripts\\rawtherapee-mcp-server.exe",
      "args": [],
      "env": {
        "RT_CLI_PATH": "C:\\Program Files\\RawTherapee\\5.11\\rawtherapee-cli.exe",
        "RT_OUTPUT_DIR": "C:\\Users\\YourName\\Pictures\\rawtherapee-output"
      }
    }
  }
}
```

**macOS** (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "/Users/yourname/.rawtherapee-mcp-env/bin/rawtherapee-mcp-server",
      "args": [],
      "env": {
        "RT_OUTPUT_DIR": "/Users/yourname/Pictures/rawtherapee-output"
      }
    }
  }
}
```

**Linux** (`~/.config/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "/home/yourname/.rawtherapee-mcp-env/bin/rawtherapee-mcp-server",
      "args": [],
      "env": {
        "RT_OUTPUT_DIR": "/home/yourname/Pictures/rawtherapee-output"
      }
    }
  }
}
```

Install the venv first if you haven't yet - see the [Installation section in README.md](../README.md#option-b----pip--venv).

### Troubleshooting

- **Server not appearing:** Fully quit Claude Desktop (it runs as a background process on macOS and Windows - closing the window is not enough), then relaunch
- **"RawTherapee not found":** Run `check_rt_status` and set `RT_CLI_PATH`
- **Config location on Windows:** `%APPDATA%` is typically `C:\Users\<name>\AppData\Roaming`
- **New version installed but tools unchanged:** See [TROUBLESHOOTING.md](TROUBLESHOOTING.md#stale-tool-list-after-update)

## Claude Code (Tested)

**Status:** Full MCP support. Images are not rendered in the terminal, but all tools work and the LLM can still analyze image data.

### Option A - uvx

```bash
claude mcp add rawtherapee -- uvx rawtherapee-mcp-server
```

### Option B - pip + venv

```bash
# Install venv first (one-time):
python3 -m venv ~/.rawtherapee-mcp-env
~/.rawtherapee-mcp-env/bin/pip install rawtherapee-mcp-server

# Register with Claude Code:
claude mcp add rawtherapee -- ~/.rawtherapee-mcp-env/bin/rawtherapee-mcp-server
```

**Windows:**

```powershell
python -m venv "$env:USERPROFILE\.rawtherapee-mcp-env"
& "$env:USERPROFILE\.rawtherapee-mcp-env\Scripts\pip.exe" install rawtherapee-mcp-server
claude mcp add rawtherapee -- "$env:USERPROFILE\.rawtherapee-mcp-env\Scripts\rawtherapee-mcp-server.exe"
```

### Notes

- Terminal-based — inline images are not displayed visually
- All processing, analysis, and profile management tools work fully
- The LLM receives the image data but cannot display it to the user
- Set environment variables in your shell before launching Claude Code

## Cursor (Untested)

**Status:** Should work — Cursor documents MCP support including ImageContent in tool responses.

### Option A - uvx

Add to `.cursor/mcp.json` in your project root:

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "uvx",
      "args": ["rawtherapee-mcp-server"],
      "env": {
        "RT_CLI_PATH": "/usr/bin/rawtherapee-cli",
        "RT_OUTPUT_DIR": "/home/you/Pictures/Processed"
      }
    }
  }
}
```

### Option B - pip + venv

Add to `.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "/home/yourname/.rawtherapee-mcp-env/bin/rawtherapee-mcp-server",
      "args": [],
      "env": {
        "RT_CLI_PATH": "/usr/bin/rawtherapee-cli",
        "RT_OUTPUT_DIR": "/home/yourname/Pictures/rawtherapee-output"
      }
    }
  }
}
```

## Windsurf (Untested)

**Status:** Should work — MCP support confirmed, image handling expected based on architecture.

### Option A - uvx

Add to your Windsurf MCP configuration:

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "uvx",
      "args": ["rawtherapee-mcp-server"],
      "env": {
        "RT_CLI_PATH": "/usr/bin/rawtherapee-cli",
        "RT_OUTPUT_DIR": "/home/you/Pictures/Processed"
      }
    }
  }
}
```

### Option B - pip + venv

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "/home/yourname/.rawtherapee-mcp-env/bin/rawtherapee-mcp-server",
      "args": [],
      "env": {
        "RT_CLI_PATH": "/usr/bin/rawtherapee-cli",
        "RT_OUTPUT_DIR": "/home/yourname/Pictures/rawtherapee-output"
      }
    }
  }
}
```

## Cline (Untested)

**Status:** MCP support present. Community reports suggest `ImageContent` may not render correctly ([#1865](https://github.com/cline/cline/issues/1865)).

### Option A - uvx

Add to your Cline MCP settings in VS Code:

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "uvx",
      "args": ["rawtherapee-mcp-server"],
      "env": {
        "RT_CLI_PATH": "/usr/bin/rawtherapee-cli",
        "RT_OUTPUT_DIR": "/home/you/Pictures/Processed"
      }
    }
  }
}
```

### Option B - pip + venv

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "/home/yourname/.rawtherapee-mcp-env/bin/rawtherapee-mcp-server",
      "args": [],
      "env": {
        "RT_CLI_PATH": "/usr/bin/rawtherapee-cli",
        "RT_OUTPUT_DIR": "/home/yourname/Pictures/rawtherapee-output"
      }
    }
  }
}
```

### Notes

- All text-based tools (EXIF, profiles, batch processing) should work
- Preview tools return file paths that can be opened manually
- The visual feedback loop may not function — verify with `preview_raw`

## Generic MCP Client

Any MCP client that supports stdio transport can use this server.

**Option A - uvx:**

```json
{
  "command": "uvx",
  "args": ["rawtherapee-mcp-server"],
  "env": {
    "RT_CLI_PATH": "/path/to/rawtherapee-cli",
    "RT_OUTPUT_DIR": "/path/to/output"
  }
}
```

**Option B - pip + venv:**

```json
{
  "command": "/home/yourname/.rawtherapee-mcp-env/bin/rawtherapee-mcp-server",
  "args": [],
  "env": {
    "RT_CLI_PATH": "/path/to/rawtherapee-cli",
    "RT_OUTPUT_DIR": "/path/to/output"
  }
}
```

For development installations, replace the `command` with `uv --directory /path/to/repo run rawtherapee-mcp-server`.

## Environment Variables

All clients support these environment variables in their `env` configuration:

| Variable | Default | Required |
|----------|---------|----------|
| `RT_CLI_PATH` | Auto-detect | Only if auto-detection fails |
| `RT_OUTPUT_DIR` | `~/Pictures/rawtherapee-mcp-output` | No |
| `RT_PREVIEW_DIR` | OS temp dir | No |
| `RT_CUSTOM_TEMPLATES_DIR` | `./custom_templates` | No |
| `RT_PREVIEW_MAX_WIDTH` | `1200` | No |
| `RT_JPEG_QUALITY` | `95` | No |
| `RT_LOG_LEVEL` | `WARNING` | No (set to `DEBUG` for troubleshooting) |

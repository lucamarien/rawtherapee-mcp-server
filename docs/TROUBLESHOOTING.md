# Troubleshooting

## Stale tool list after update

**Symptom:** You updated the server (via `uv cache clean` + version pin change, or via `pip install --upgrade`), the version string reported by `check_rt_status` looks correct, but new tools from the release notes are not visible in Claude Desktop.

**Cause - two-layer caching:**

1. The server package cache (uvx's receipt or your pip venv)
2. Claude Desktop's tool-list cache for the MCP server

Both must be invalidated for new tools to appear. A correct version string in `check_rt_status` means the package updated, but it does NOT mean Claude Desktop has refreshed its tool inventory.

### Step 1 - verify what the installed package actually contains

Install the published version into a throwaway venv and inspect directly:

**Linux / macOS:**

```bash
python3 -m venv /tmp/rt-inspect
/tmp/rt-inspect/bin/pip install rawtherapee-mcp-server==1.0.4
/tmp/rt-inspect/bin/python -c "
from rawtherapee_mcp.server import mcp
import asyncio
tools = asyncio.run(mcp.list_tools())
print(f'{len(tools)} tools registered:')
for t in sorted(tools, key=lambda x: x.name):
    print(f'  {t.name}')
"
```

**Windows (PowerShell):**

```powershell
python -m venv C:\temp\rt-inspect
& C:\temp\rt-inspect\Scripts\pip.exe install rawtherapee-mcp-server==1.0.4
& C:\temp\rt-inspect\Scripts\python.exe -c @"
from rawtherapee_mcp.server import mcp
import asyncio
tools = asyncio.run(mcp.list_tools())
print(f'{len(tools)} tools registered:')
[print(f'  {t.name}') for t in sorted(tools, key=lambda x: x.name)]
"@
```

Expected output: `49 tools registered:` followed by the full list including the v1.0.3 additions (`apply_lens_correction`, `list_luts`, `strip_metadata`, `create_profile_variant`, etc.).

### Step 2 - compare against what Claude Desktop sees

In a chat, ask Claude: "List all rawtherapee tools you have available."

### Outcome table

| Package has | Claude sees | Fix |
|-------------|-------------|-----|
| Expected count | Expected count | Working correctly |
| Expected count | Fewer tools | Client cache is stale - see [Nuclear restart](#nuclear-restart) below |
| Fewer than expected | Any | Wrong version or wrong install location - check `pip show rawtherapee-mcp-server` or `uvx rawtherapee-mcp-server@1.0.4 --help` |

---

## Nuclear restart

When a regular restart does not refresh the tool list, clear Claude Desktop's application cache. This preserves your `claude_desktop_config.json`.

**Windows (PowerShell):**

```powershell
Get-Process *claude* -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item "$env:APPDATA\Claude\Cache" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "$env:APPDATA\Claude\Code Cache" -Recurse -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 3
Start-Process "$env:LOCALAPPDATA\AnthropicClaude\Claude.exe"
```

**macOS:**

```bash
osascript -e 'quit app "Claude"'
sleep 2
rm -rf ~/Library/Application\ Support/Claude/Cache
rm -rf ~/Library/Application\ Support/Claude/Code\ Cache
open -a Claude
```

**Linux:**

```bash
pkill -f claude
sleep 2
rm -rf ~/.config/Claude/Cache
rm -rf ~/.config/Claude/Code\ Cache
claude &
```

---

## Switching between uvx and pip

The two install methods use separate locations and do not interfere with each other. Switch by editing the `command` and `args` in `claude_desktop_config.json` to point at the new method, then fully quit and restart Claude Desktop.

To remove the method you are no longer using:

- **Remove uvx cache:** `uv cache clean rawtherapee-mcp-server`
- **Remove pip venv (Linux / macOS):** `rm -rf ~/.rawtherapee-mcp-env`
- **Remove pip venv (Windows):** `Remove-Item "$env:USERPROFILE\.rawtherapee-mcp-env" -Recurse -Force`

---

## Server starts but reports wrong RT path

The server resolves the RawTherapee CLI via the `RT_CLI_PATH` environment variable first, then falls back to `PATH` lookup. If `check_rt_status` reports `installed: false`, add `RT_CLI_PATH` to the `env` block of your `claude_desktop_config.json` entry:

```json
"env": {
  "RT_CLI_PATH": "C:\\Program Files\\RawTherapee\\5.12\\rawtherapee-cli.exe"
}
```

Common paths:

- Windows: `C:\Program Files\RawTherapee\5.12\rawtherapee-cli.exe` (version number in path varies)
- macOS: `/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli`
- Linux: `/usr/bin/rawtherapee-cli` or `/snap/bin/rawtherapee-cli`

---

## uvx shows old version after --refresh

`uvx --refresh rawtherapee-mcp-server` re-downloads packages but re-uses the pinned version from the local receipt. It does not upgrade to a new release. To actually get a new version:

1. Clear the receipt: `uv cache clean rawtherapee-mcp-server`
2. Update the version pin in `claude_desktop_config.json` (e.g. `@1.0.4` → `@1.0.5`)
3. Fully quit and restart Claude Desktop

The unpinned form (`"rawtherapee-mcp-server"` with no `@version`) behaves the same way - it pins on first run and never upgrades automatically. Always pin explicitly.

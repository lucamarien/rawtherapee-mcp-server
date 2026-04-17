# RawTherapee MCP Server

[![CI](https://github.com/lucamarien/rawtherapee-mcp-server/actions/workflows/ci.yml/badge.svg)](https://github.com/lucamarien/rawtherapee-mcp-server/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rawtherapee-mcp-server)](https://pypi.org/project/rawtherapee-mcp-server/)
[![Python](https://img.shields.io/pypi/pyversions/rawtherapee-mcp-server)](https://pypi.org/project/rawtherapee-mcp-server/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Cross-platform [Model Context Protocol](https://modelcontextprotocol.io/) (MCP) server for AI-assisted RAW photo development via [RawTherapee](https://rawtherapee.com/) CLI. Provides **49 tools** for profile generation, image processing, visual previews, batch operations, device presets, luminance-based local adjustments, lens correction, film simulation LUTs, profile inheritance, and metadata privacy.

**What makes it unique:** The LLM can *see* the photos it's editing. Preview tools return inline Base64 images via MCP's ImageContent protocol, creating a visual feedback loop where the AI analyzes the image, adjusts settings, previews the result, and iterates — just like a human editor.

## MCP Client Compatibility

Not all MCP clients handle inline images the same way. The visual feedback loop requires a client that renders `ImageContent` from tool responses and a backing LLM with vision capabilities.

| Client | MCP Support | Image Display | Visual Workflow | Status |
|--------|------------|---------------|----------------|--------|
| **Claude Desktop** | Full | Yes | Full | Tested |
| **Claude Code** | Full | No (terminal) | Partial | Tested — images not rendered in terminal, but processing and text analysis work fully |
| **Cursor** | Full | Should work | Should work | Untested — MCP docs indicate ImageContent support |
| **Windsurf** | Full | Should work | Should work | Untested |
| **Cline** | Partial | Unknown | Unknown | Untested — community reports suggest ImageContent may not render ([#1865](https://github.com/cline/cline/issues/1865)) |
| **Zed** | Full | Unknown | Unknown | Untested |

**Minimum requirements for the full visual workflow:**
- MCP client renders `ImageContent` (type: "image", data: base64, mimeType: "image/jpeg") from tool responses
- Backing LLM supports vision/image analysis (e.g. Claude with vision)
- Tool response size accommodates ~150KB previews (most clients: 1MB limit)

**Text-only clients:** All 49 tools work without inline images. Preview tools return file paths instead. The LLM can still read EXIF metadata, histogram statistics, generate profiles, batch process, and use luminance presets — the visual feedback loop is the only feature that requires image support.

## Prerequisites

- Python 3.11+
- [RawTherapee](https://rawtherapee.com/) 5.9+ with CLI component installed
- An MCP-compatible client (see table above)

## Installation

### From PyPI

```bash
pip install rawtherapee-mcp-server
```

### From source

```bash
git clone https://github.com/lucamarien/rawtherapee-mcp-server
cd rawtherapee-mcp-server
pip install -e ".[dev]"
```

## Client Configuration

### Claude Desktop

The RawTherapee CLI path is auto-detected on most systems. Set `RT_CLI_PATH` if auto-detection fails or RawTherapee is in a non-standard location.

<details>
<summary><strong>Windows</strong> (<code>%APPDATA%\Claude\claude_desktop_config.json</code>)</summary>

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

</details>

<details>
<summary><strong>macOS</strong> (<code>~/Library/Application Support/Claude/claude_desktop_config.json</code>)</summary>

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

</details>

<details>
<summary><strong>Linux</strong> (<code>~/.config/Claude/claude_desktop_config.json</code>)</summary>

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

RT CLI is auto-detected at `/usr/bin/rawtherapee-cli`, `/usr/local/bin/rawtherapee-cli`, or `/snap/bin/rawtherapee-cli`.

</details>

<details>
<summary><strong>Development (from source)</strong></summary>

Use `uv` to run from the cloned repository:

```json
{
  "mcpServers": {
    "rawtherapee": {
      "command": "uv",
      "args": ["--directory", "/path/to/rawtherapee-mcp-server", "run", "rawtherapee-mcp-server"],
      "env": {
        "RT_OUTPUT_DIR": "/home/you/Pictures/Processed"
      }
    }
  }
}
```

</details>

### Claude Code

```bash
# Published package
claude mcp add rawtherapee -- uvx rawtherapee-mcp-server

# Development (from source)
claude mcp add rawtherapee -- uv --directory /path/to/rawtherapee-mcp-server run rawtherapee-mcp
```

### Cursor

Add to `.cursor/mcp.json` in your project:

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

### Windsurf

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

### Cline (VS Code)

Add to your Cline MCP settings:

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

> **Note:** Cline may not render inline images from tool responses. All text-based tools work normally.

## Quick Start

After installation and client configuration, try this workflow:

1. **"Analyze this photo"** — `analyze_image` reads EXIF, computes histogram, generates a thumbnail, and returns processing recommendations
2. **"Make it warmer with more contrast"** — `generate_pp3_profile` creates a profile with warm white balance and contrast boost, `preview_before_after` shows the difference
3. **"The shadows are too dark"** — `add_luminance_adjustment` adds a shadow recovery spot, `preview_with_adjustments` shows the result
4. **"Export for my phone"** — `process_raw` with `device_preset` crops and processes at the right aspect ratio

## Updating

The package uses `uvx` which caches installed environments. To get updates:

**Recommended:** Pin to specific versions for stability:

```json
"args": ["rawtherapee-mcp-server@1.0.3"]
```

Update the version number when you want to upgrade.

**Alternative:** Use `@latest` to attempt auto-updates (cache may interfere):

```json
"args": ["rawtherapee-mcp-server@latest"]
```

Restart Claude Desktop to pick up new versions.

**Force update:**

```bash
uvx --force-reinstall rawtherapee-mcp-server
```

Check [GitHub Releases](https://github.com/lucamarien/rawtherapee-mcp-server/releases) for changelogs and upgrade notes.

## Available Tools (49)

### Discovery & Configuration (5)

| Tool | Description |
|------|-------------|
| `check_rt_status` | Check RawTherapee installation, version, CLI path, and server configuration |
| `list_templates` | List all available PP3 templates (built-in and custom) |
| `list_device_presets` | List all device/format crop and resize presets |
| `list_raw_files` | Scan a directory for supported RAW files |
| `list_output_files` | List processed output files in the output directory |

### Metadata & Analysis (5)

| Tool | Description |
|------|-------------|
| `read_exif` | Read EXIF metadata with structured processing recommendations |
| `analyze_image` | All-in-one analysis: EXIF + histogram + thumbnail + recommendations |
| `batch_analyze` | Analyze multiple images with EXIF, recommendations, and thumbnails |
| `get_image_info` | Get dimensions, format, file size with optional inline thumbnail |
| `get_histogram` | RGB histogram with per-channel statistics, clipping, and SVG visualization |

### Profile Management (8)

| Tool | Description |
|------|-------------|
| `generate_pp3_profile` | Create a PP3 profile from base template + parameters + device preset |
| `read_profile` | Display PP3 profile contents in human-readable format |
| `adjust_profile` | Modify specific parameters in an existing profile |
| `compare_profiles` | Diff two profiles with optional visual A/B comparison |
| `save_template` | Save a profile as a reusable custom template |
| `create_template_from_description` | Create a template stub from natural language description |
| `delete_template` | Delete a custom template |
| `interpolate_profiles` | Blend two profiles by linear interpolation |

### Preview & Visualization (7)

| Tool | Description |
|------|-------------|
| `preview_raw` | Quick preview JPEG with optional inline image return |
| `preview_before_after` | Side-by-side neutral vs. profile comparison |
| `preview_exposure_bracket` | Multiple EV stops rendered for exposure comparison |
| `preview_white_balance` | Multiple WB presets with Kelvin values |
| `batch_preview` | Thumbnails for multiple RAW files |
| `preview_luminance_mask` | Grayscale mask showing local adjustment coverage |
| `preview_with_adjustments` | Preview with all Locallab spots active |

### Processing & Export (4)

| Tool | Description |
|------|-------------|
| `process_raw` | Process a RAW file to JPEG/TIFF/PNG with inline thumbnail |
| `apply_template` | Apply a template to process a RAW file with optional device preset |
| `batch_process` | Process multiple RAW files with the same profile |
| `export_multi_device` | Export one RAW optimized for multiple devices in one call |

### Crop & Device (3)

| Tool | Description |
|------|-------------|
| `adjust_crop_position` | Reposition crop (left/center/right, top/center/bottom, or pixel offsets) |
| `add_device_preset_tool` | Create a custom device preset |
| `delete_device_preset` | Delete a custom device preset |

### Local Adjustments (5)

| Tool | Description |
|------|-------------|
| `add_luminance_adjustment` | Add luminance-based local adjustment (shadows/midtones/highlights/custom) |
| `list_local_adjustments` | List all Locallab spots in a profile |
| `adjust_local_spot` | Modify an existing Locallab spot |
| `remove_local_adjustment` | Remove a Locallab spot |
| `apply_local_preset` | Apply a predefined local adjustment preset with intensity scaling |

### Lens Correction (2)

| Tool | Description |
|------|-------------|
| `apply_lens_correction` | Apply Lensfun auto-detect or Adobe LCP correction to a PP3 profile |
| `check_lens_support` | Query the Lensfun database for distortion/vignetting/TCA coverage |

### Film Simulation / LUT Support (4)

| Tool | Description |
|------|-------------|
| `list_luts` | Scan `RT_HALDCLUT_DIR` for HaldCLUT film simulation LUTs, grouped by category |
| `apply_lut` | Write a HaldCLUT film simulation into a PP3 profile with configurable strength |
| `preview_lut` | Render an inline preview of a RAW file with a film simulation applied |
| `preview_lut_comparison` | Render 2–5 LUT previews side-by-side for quick comparison |

### Profile Inheritance (3)

| Tool | Description |
|------|-------------|
| `create_profile_variant` | Derive a child PP3 from a parent template with section-level overrides |
| `list_profile_variants` | List all variants with override summaries, optionally filtered by parent |
| `update_base_profile` | Modify a base template and propagate changes to all child variants |

### Metadata Privacy (3)

| Tool | Description |
|------|-------------|
| `inspect_metadata` | Classify JPEG/TIFF EXIF into sensitive/technical/rights buckets with privacy recommendations |
| `strip_metadata` | Losslessly remove GPS, serial numbers, software, and owner tags from a JPEG |
| `set_metadata` | Write copyright, artist, description, and keywords into a JPEG |

## Built-in Resources

### PP3 Templates (5)

| Template | Description |
|----------|-------------|
| `neutral` | Minimal processing, camera white balance, basic sharpening |
| `warm_portrait` | Warm tones (5800K), gentle contrast, skin-friendly saturation |
| `moody_cinematic` | Cool tones (5200K), lifted blacks, reduced saturation, film look |
| `vivid_pet` | Warm tones (5600K), boosted saturation and vibrance, strong sharpening |
| `bw_classic` | Black & white via channel mixer, high contrast, strong sharpening |

### Device Presets (19)

- **Mobile** (7): Samsung Galaxy S26 Ultra, Galaxy S25 Ultra, iPhone 16 Pro Max, iPhone 16, Google Pixel 9 Pro, generic 9:16, generic 9:19.5
- **Desktop** (5): 4K UHD (3840x2160), WQHD (2560x1440), Full HD (1920x1080), Ultrawide 21:9 (3440x1440), Dual 4K 32:9 (7680x2160)
- **Photo Formats** (7): 3:2 (35mm), 4:3, 16:9, 1:1 (square), 5:4, 4:5 (Instagram portrait), 2:3 (portrait 35mm)

Custom presets can be added via `add_device_preset_tool` and persist across sessions.

### Local Adjustment Presets (7)

| Preset | Description |
|--------|-------------|
| `shadow_recovery` | Brighten shadows without affecting highlights |
| `highlight_protection` | Compress highlights to recover detail |
| `split_tone_warm_cool` | Warm shadows, cool highlights |
| `midtone_contrast` | Add contrast to midtones only |
| `shadow_desaturation` | Desaturate shadow areas for a clean look |
| `amoled_optimize` | High contrast and deep blacks for AMOLED displays |
| `hdr_natural` | Natural HDR look with lifted shadows and compressed highlights |

Presets accept an `intensity` parameter (50 = default, 25 = half, 100 = double).

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `RT_CLI_PATH` | Auto-detect | Path to `rawtherapee-cli` binary |
| `RT_OUTPUT_DIR` | `~/Pictures/rawtherapee-mcp-output` | Default output directory |
| `RT_PREVIEW_DIR` | OS temp dir | Preview image directory |
| `RT_CUSTOM_TEMPLATES_DIR` | `./custom_templates` | Custom PP3 templates directory |
| `RT_PREVIEW_MAX_WIDTH` | `1200` | Max preview width in pixels |
| `RT_JPEG_QUALITY` | `95` | Default JPEG quality (1-100) |
| `RT_LOG_LEVEL` | `WARNING` | Logging level (DEBUG, INFO, WARNING, ERROR) |

See [.env.example](.env.example) for a documented configuration template.

## Known Limitations

- **RawTherapee CLI must be installed separately** — it is not a Python package and cannot be installed via pip
- **stdio transport only** — designed for local desktop use, no HTTP/SSE server mode
- **RT 5.12 crop+resize bug** — RawTherapee 5.12 silently ignores Crop when Resize is also enabled in the same PP3 profile; the server applies a crop-only workaround automatically
- **1MB MCP tool response limit** — preview resolution is managed to stay within Claude Desktop's response size limit
- **No pixel-level editing** — no retouching, object removal, frequency separation, or content-aware fill
- **No multi-image compositing** — no HDR merge, panorama stitching, or focus stacking
- **Luminance masks are tonal only** — no spatial or subject-aware masking
- Integration tests require a RawTherapee installation and are skipped by default

## Troubleshooting

**RawTherapee not found:**
- Run `check_rt_status` to see detection details
- Set `RT_CLI_PATH` to the full path of `rawtherapee-cli`:
  - Windows: `C:\Program Files\RawTherapee\5.11\rawtherapee-cli.exe`
  - macOS: `/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli`
  - Linux: `/usr/bin/rawtherapee-cli`

**Paths with spaces on Windows:**
- Always use the full path in `RT_CLI_PATH`, including quotes if your shell requires them
- Environment variables in MCP client config JSON do not need extra escaping

**Preview images too large:**
- Reduce `RT_PREVIEW_MAX_WIDTH` (default: 1200)
- Preview tools auto-thumbnail to stay within the 1MB response limit

**Server not responding:**
- Verify the entry in your MCP client config is correct
- Restart your MCP client after config changes
- Set `RT_LOG_LEVEL=DEBUG` to see detailed logs on stderr

## Docker

```bash
docker build -t rawtherapee-mcp-server .
docker run -i --rm \
  -v /path/to/photos:/photos \
  -v /path/to/output:/output \
  -e RT_OUTPUT_DIR=/output \
  rawtherapee-mcp-server
```

## Development

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for full setup instructions.

```bash
git clone https://github.com/lucamarien/rawtherapee-mcp-server
cd rawtherapee-mcp-server
pip install -e ".[dev]"
make validate    # lint + format + typecheck + test + security + audit
```

### Testing

```bash
# Unit tests (mocked, no RawTherapee required)
pytest -v

# Integration tests (requires RawTherapee installation)
pytest -m integration -v
```

### MCP Inspector

```bash
npx @modelcontextprotocol/inspector uv run rawtherapee-mcp
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines, coding standards, and PR checklist.

## License

[MIT](LICENSE)

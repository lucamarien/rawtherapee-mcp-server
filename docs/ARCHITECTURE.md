# Architecture

## Overview

The RawTherapee MCP Server is a [Model Context Protocol](https://modelcontextprotocol.io/) server that bridges an LLM (via an MCP client) with RawTherapee's command-line interface for RAW photo development.

```
MCP Client (Claude Desktop, Cursor, etc.)
    │
    │  MCP JSON-RPC over stdio
    ▼
FastMCP Server (server.py)
    │
    ├── Profile Management (pp3_parser.py, pp3_generator.py)
    ├── EXIF Analysis (exif_reader.py)
    ├── Histogram & Thumbnails (histogram.py, image_utils.py)
    ├── Device Presets (device_presets.py)
    ├── Local Adjustments (locallab.py)
    │
    └── rawtherapee-cli (subprocess)
            │
            └── RAW file → Processed JPEG/TIFF/PNG
```

## Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| MCP Framework | FastMCP >= 2.0 |
| Build System | Hatchling |
| Transport | stdio (JSON-RPC over stdin/stdout) |
| RAW Processor | RawTherapee CLI (external subprocess) |
| EXIF Parsing | exifread library + TIFF IFD fallback |
| Image Processing | Pillow (thumbnails and histograms only) |

## Module Responsibilities

```
src/rawtherapee_mcp/
├── __init__.py          # Package version (__version__)
├── __main__.py          # Entry: python -m rawtherapee_mcp
├── server.py            # FastMCP server, all 37 tool registrations, main()
├── config.py            # Configuration loading from environment variables
├── rt_cli.py            # rawtherapee-cli subprocess wrapper (async)
├── pp3_parser.py        # Custom PP3 profile reader/writer
├── pp3_generator.py     # Profile generation from parameter dicts + templates
├── exif_reader.py       # EXIF extraction, dimension parsing, recommendations
├── histogram.py         # RGB histogram computation and SVG rendering
├── image_utils.py       # JPEG thumbnail generation via Pillow
├── device_presets.py    # Device/format crop presets (built-in + custom)
├── locallab.py          # Locallab spot management and luminance masks
└── templates/           # 5 built-in PP3 templates
    ├── __init__.py
    ├── neutral.pp3
    ├── warm_portrait.pp3
    ├── moody_cinematic.pp3
    ├── vivid_pet.pp3
    └── bw_classic.pp3
```

### server.py

The central module registering all 37 MCP tools via `@mcp.tool()` decorators. Uses FastMCP's lifespan context manager to initialize configuration on startup. Tools return `dict[str, Any]` for text responses or `ToolResult` with `ImageContent` for inline image responses.

### config.py

Loads configuration from environment variables only (no `.env` file reading). Implements cross-platform auto-detection of the RawTherapee CLI:

- **Windows:** Scans `Program Files\RawTherapee\` subdirectories
- **macOS:** Checks `/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli`
- **Linux:** Checks `/usr/bin/`, `/usr/local/bin/`, `/snap/bin/`

Returns a frozen `RTConfig` dataclass passed to all tools via the MCP context.

### pp3_parser.py

Custom INI-like parser for RawTherapee's PP3 profile format. Standard Python `configparser` cannot be used because PP3 files use semicolons as value separators in curve definitions (e.g., `Curve=1;0.0;0.0;0.5;0.5;1.0;1.0;`), which `configparser` treats as inline comments.

Key operations: `load`/`save`, `get`/`set`, `merge`, `diff`, `interpolate`, `copy`.

### pp3_generator.py

Translates friendly parameter names (e.g., `{"exposure": {"compensation": 0.5}}`) to raw PP3 section/key pairs (e.g., `[Exposure] Compensation=0.5`). Handles template loading, device preset application, and the RT 5.12 crop+resize workaround.

### exif_reader.py

Extracts EXIF metadata using the `exifread` library. Includes a TIFF IFD fallback parser for RAW formats (particularly Canon CR2) where `exifread` may not return image dimensions. Also generates structured processing recommendations (ISO-based noise reduction, aperture-based sharpening suggestions).

### locallab.py

Manages RawTherapee's Locallab local adjustment system. Each "spot" represents a luminance-masked adjustment with ~120 PP3 keys. This module abstracts the complexity into simple operations: add/read/update/remove spots, convert luminance ranges to RT curve strings, and apply predefined presets.

## Key Architectural Decisions

### Inline Image Return

Preview tools return Base64 JPEG images via MCP's `ImageContent` protocol. This enables the LLM to visually inspect processing results and iterate on settings — the core value proposition. Images are thumbnailed to ~600px width at Q80 to stay within the 1MB MCP tool response limit.

### Crop-Only for Device Presets

RawTherapee 5.12 has a CLI bug where enabling both Crop and Resize in the same PP3 profile causes Crop to be silently ignored. The server works around this by using crop-only profiles (Resize disabled) when a device preset is applied. The output is larger than the target resolution — the device scales it natively.

### EXIF-Aware Crop Calculation

When applying a device preset with `file_path`, the server reads the image's EXIF orientation to determine effective dimensions, then calculates an aspect-ratio-based centered crop. This ensures correct cropping regardless of camera orientation.

### SVG Histograms

Histogram visualization uses inline SVG strings rather than matplotlib. This eliminates a heavy dependency and produces lightweight, embeddable visualizations using only Pillow's `Image.histogram()` for the raw data.

### Single PP3 Merging

RT 5.12 can stack-overflow when merging multiple PP3 profiles via `-p a.pp3 -p b.pp3`. The server always merges into a single combined PP3 before passing it to the CLI.

### Graceful Degradation

All tools work without inline images — clients that don't support `ImageContent` receive file paths instead. The server also starts and functions (in limited capacity) without RawTherapee installed, returning helpful error messages directing users to install it.

## PP3 Profile Format

PP3 is RawTherapee's processing profile format, similar to INI files:

```ini
[Version]
AppVersion=5.11
Version=351

[Exposure]
Compensation=0.5
Brightness=10
Contrast=20

[White Balance]
Setting=Custom
Temperature=5800

[Crop]
Enabled=true
X=100
Y=200
W=3000
H=2000

[Resize]
Enabled=false
```

Profiles define all processing parameters. The server creates, reads, modifies, merges, diffs, and interpolates these profiles programmatically.

## Data Flow: Processing a RAW File

1. Client sends `process_raw(file_path, profile_path)` via MCP
2. `server.py` validates inputs and checks for crop+resize conflict
3. `rt_cli.py` constructs the command: `rawtherapee-cli -p profile.pp3 -o output.jpg -j95 -Y -q -c input.cr2`
4. Subprocess runs via `asyncio.to_thread()` with 300-second timeout
5. On success, `image_utils.py` generates a JPEG thumbnail
6. Response returned as `ToolResult` with text metadata + inline image

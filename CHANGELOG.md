# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2026-04-15

### Added

#### Discovery & Configuration (5 tools)

- `check_rt_status` — Check RawTherapee installation status, version, CLI path, and server configuration
- `list_templates` — List all available PP3 processing templates (built-in and custom)
- `list_device_presets` — List all device/format crop and resize presets
- `list_raw_files` — Scan a directory for supported RAW image files (25+ formats)
- `list_output_files` — List processed output files in the output directory

#### Metadata & Analysis (5 tools)

- `read_exif` — Read EXIF metadata with structured processing recommendations
- `analyze_image` — Comprehensive single-call analysis: EXIF + histogram + thumbnail + recommendations
- `batch_analyze` — Batch analysis of multiple images with EXIF, recommendations, and thumbnails
- `get_image_info` — Get dimensions, format, file size, and bit depth with optional inline thumbnail
- `get_histogram` — RGB histogram computation with per-channel statistics, clipping analysis, and SVG visualization

#### Profile Management (8 tools)

- `generate_pp3_profile` — Create PP3 profiles from base templates, custom parameters, and device presets
- `read_profile` — Display PP3 profile contents in human-readable format
- `adjust_profile` — Modify specific parameters in an existing PP3 profile (friendly names or raw PP3 keys)
- `compare_profiles` — Diff two PP3 profiles with optional visual A/B comparison
- `save_template` — Save a PP3 profile as a reusable custom template
- `create_template_from_description` — Create a PP3 template stub from natural language style description
- `delete_template` — Delete a custom PP3 template
- `interpolate_profiles` — Blend two PP3 profiles by linear interpolation with adjustable factor

#### Preview & Visualization (7 tools)

- `preview_raw` — Generate a small preview JPEG with optional inline image return
- `preview_before_after` — Side-by-side neutral vs. profile comparison
- `preview_exposure_bracket` — Simulate exposure bracketing at multiple EV stops
- `preview_white_balance` — Preview multiple white balance presets with Kelvin values
- `batch_preview` — Generate small preview thumbnails for multiple RAW files
- `preview_luminance_mask` — Visualize which image areas a local adjustment targets (grayscale mask)
- `preview_with_adjustments` — Preview with all active Locallab spots applied, optional histogram

#### Processing & Export (4 tools)

- `process_raw` — Process a RAW file to JPEG/TIFF/PNG with a PP3 profile and inline thumbnail
- `apply_template` — Apply a template to process a RAW file, with optional device preset
- `batch_process` — Process multiple RAW files with the same profile and settings
- `export_multi_device` — Export one RAW file optimized for multiple devices in a single call

#### Crop & Device (3 tools)

- `adjust_crop_position` — Reposition crop area with semantic directions (left/center/right, top/center/bottom) or pixel offsets
- `add_device_preset_tool` — Create and persist a custom device/format preset
- `delete_device_preset` — Delete a custom device preset

#### Local Adjustments (5 tools)

- `add_luminance_adjustment` — Add luminance-based local adjustment spots (shadows/midtones/highlights/custom)
- `list_local_adjustments` — List all Locallab spots in a PP3 profile with parameters
- `adjust_local_spot` — Modify parameters, luminance range, strength, or enabled state of a spot
- `remove_local_adjustment` — Remove a Locallab spot and re-index remaining spots
- `apply_local_preset` — Apply predefined local adjustment presets with scalable intensity

### Features

- 5 built-in PP3 templates: neutral, warm_portrait, moody_cinematic, vivid_pet, bw_classic
- 19 built-in device presets across mobile (7), desktop (5), and photo formats (7)
- 7 local adjustment presets: shadow_recovery, highlight_protection, split_tone_warm_cool, midtone_contrast, shadow_desaturation, amoled_optimize, hdr_natural
- Inline image return via MCP ImageContent for visual feedback loop
- Custom PP3 parser with semicolon value handling (configparser incompatible)
- Cross-platform RT CLI auto-detection (Windows, macOS, Linux)
- SVG histogram rendering without matplotlib dependency
- EXIF-based structured processing recommendations (ISO to denoise, aperture to sharpening)
- Direct TIFF IFD parsing fallback for RAW dimensions (Canon CR2, etc.)
- RT 5.12 crop-only workaround for crop+resize incompatibility
- Custom template and device preset persistence across sessions
- Graceful degradation when RawTherapee is not installed
- Support for 25+ RAW formats (CR2, CR3, NEF, ARW, DNG, RAF, ORF, RW2, and more)

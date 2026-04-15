# Workflow Examples

Concrete end-to-end workflows showing how the tools work together. These examples assume you're using an MCP client with inline image support (e.g., Claude Desktop).

## Basic RAW Processing

The simplest workflow: analyze, create a profile, preview, process.

```
You: "Analyze IMG_1234.CR2"
→ analyze_image returns EXIF, histogram, thumbnail, and recommendations

You: "Create a warm portrait look"
→ generate_pp3_profile(name="warm_edit", base_template="warm_portrait")

You: "Show me a preview"
→ preview_raw(file_path="IMG_1234.CR2", profile_path="warm_edit.pp3")
→ Returns inline image for visual inspection

You: "Looks good, process it"
→ process_raw(file_path="IMG_1234.CR2", profile_path="warm_edit.pp3")
→ Full-resolution JPEG saved to output directory
```

## Iterative Editing with Visual Feedback

The visual feedback loop — the LLM sees each change and adjusts.

```
You: "Make this photo look cinematic"
→ generate_pp3_profile(name="cinematic", base_template="moody_cinematic")
→ preview_before_after(file_path, profile_path) — shows neutral vs. cinematic side by side

You: "Too dark, bring up the shadows"
→ adjust_profile(profile_path, adjustments={"exposure": {"compensation": 0.3}})
→ preview_raw — LLM sees the adjustment

You: "The highlights are still too bright"
→ add_luminance_adjustment(profile_path, adjustment_type="highlights",
    parameters={"highlight_compression": 200})
→ preview_with_adjustments — LLM verifies the local adjustment

You: "Perfect, export it"
→ process_raw(file_path, profile_path)
```

## Batch Processing a Photo Session

Process multiple RAW files with consistent settings.

```
You: "Show me all RAW files in /photos/session/"
→ list_raw_files(directory="/photos/session/", recursive=true)
→ Returns 45 CR2 files

You: "Preview the first 8"
→ batch_preview(file_paths=[first 8 paths], include_exif=true)
→ Returns 8 thumbnails with ISO/aperture/shutter info

You: "These are outdoor portraits, apply warm_portrait to all"
→ batch_process(file_paths=[all 45 paths], profile_path=...,
    output_format="jpeg")
→ Processes all 45 files with progress tracking
```

## Template Creation and Reuse

Create a custom style and save it for future use.

```
You: "I want a faded film look with lifted blacks and muted colors"
→ create_template_from_description(name="faded_film",
    description="Lifted blacks, reduced saturation, warm shadows")
→ Creates neutral base template

→ adjust_profile(profile_path, adjustments={
    "exposure": {"black": 30, "contrast": -10},
    "color": {"saturation": -20, "vibrance": -10},
    "white_balance": {"temperature": 5600}
  })
→ preview_raw — verify the look

→ save_template(profile_path, name="faded_film",
    description="Faded film with lifted blacks and muted colors")
→ Template saved and available for future sessions

You: (next session) "Apply my faded_film template to this photo"
→ apply_template(file_path, template_name="faded_film")
```

## Device-Specific Export

Export a photo optimized for different devices.

```
You: "Export this for my Galaxy S26 Ultra and as a 4K desktop wallpaper"
→ export_multi_device(file_path, profile_path,
    device_presets=["galaxy_s26_ultra", "4k_uhd"])
→ Two files created: one cropped to 9:19.5 for the phone,
  one cropped to 16:9 at 4K for the desktop

You: "Move the phone crop to the right — the subject is on the right side"
→ adjust_crop_position(profile_path, file_path,
    horizontal="right", vertical="center")
→ Preview shows the repositioned crop
```

## Local Adjustments (Shadow Recovery)

Use luminance-based local adjustments for selective editing.

```
You: "The shadows are too dark but the sky looks fine"
→ add_luminance_adjustment(profile_path,
    adjustment_type="shadows",
    parameters={"exposure": 1.0, "contrast": 10})
→ Adds a Locallab spot targeting 0-30% luminance

→ preview_luminance_mask(file_path, profile_path, spot_index=0)
→ Grayscale mask showing which areas are affected

→ preview_with_adjustments(file_path, profile_path)
→ Full preview with the shadow recovery applied

You: "Also add some warmth to the highlights"
→ add_luminance_adjustment(profile_path,
    adjustment_type="highlights",
    parameters={"white_balance_shift": 200})
```

## Split Toning with Presets

Apply predefined local adjustment presets for common effects.

```
You: "Add a warm/cool split tone"
→ apply_local_preset(profile_path, preset="split_tone_warm_cool", intensity=50)
→ Adds two Locallab spots: warm shadows + cool highlights

You: "Make the effect stronger"
→ apply_local_preset(profile_path, preset="split_tone_warm_cool", intensity=100)
→ Double-strength split tone

→ preview_with_adjustments(file_path, profile_path, include_histogram=true)
→ Preview + histogram statistics for the result
```

## Comparing Processing Styles

Compare different approaches before committing.

```
You: "Compare warm_portrait and moody_cinematic on this photo"
→ generate_pp3_profile(name="option_a", base_template="warm_portrait")
→ generate_pp3_profile(name="option_b", base_template="moody_cinematic")
→ compare_profiles(profile_a="option_a.pp3", profile_b="option_b.pp3",
    file_path, include_preview=true)
→ Returns text diff + two inline preview images

You: "Something in between"
→ interpolate_profiles(profile_a="option_a.pp3", profile_b="option_b.pp3",
    factor=0.4, file_path=..., include_preview=true)
→ Blended profile at 40% toward cinematic
```

## Exposure Exploration

Find the right exposure without processing at full resolution.

```
You: "This photo looks underexposed, show me some options"
→ preview_exposure_bracket(file_path,
    stops=[-1.0, -0.5, 0.0, 0.5, 1.0, 1.5])
→ Six preview images at different EV values

You: "+1.0 looks best"
→ generate_pp3_profile(name="corrected",
    parameters={"exposure": {"compensation": 1.0}})
```

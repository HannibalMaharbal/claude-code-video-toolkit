# Blender CLI prototype

Local headless path for importing a 3D asset, checking the scene, and rendering
an MP4 that can be used as a clip in a video-toolkit project. Blender's bundled
Python API renders PNG frames and the already installed local FFmpeg encodes the
MP4; no Python package installation is required.

```sh
blender -b --gpu-backend metal --python-exit-code 1 -noaudio \
  -P tools/blender_cli/run_pipeline.py -- \
  --input /path/to/product.glb \
  --output-dir projects/blender-prototype \
  --frames 72 --fps 24 --width 1280 --height 720 --save-scene
```

Supported inputs: `.blend`, `.fbx`, `.glb`, `.gltf`, `.obj`, `.stl`, and ZIP
archives containing exactly one GLB (the Meshy download workflow). A `.blend`
input contributes its objects to a clean scene; other formats are imported into
one. The prototype fits a camera to mesh bounds, adds area lights when needed,
checks for meshes/camera/render settings, renders PNG frames, then encodes an
H.264 MP4 with local FFmpeg. Default output is 1280×720 at 24 fps for 3 seconds.

The script never publishes or uploads output. It creates the output directory
when needed and refuses missing inputs, unsupported types, invalid dimensions,
or non-MP4 destinations. Keep generated renders and source assets under the
gitignored `projects/` directory.

## Pipeline boundary

Codex and Claude Code can invoke this CLI and inspect its machine-readable
`SCENE_OK` / `EXPORT_OK` status lines followed by one machine-readable
`PIPELINE_RESULT {json}` line. On pipeline failure it writes
`PIPELINE_ERROR {json}` to stderr and exits with code 1. Invalid CLI arguments
use argparse's standard nonzero exit. See [AGENT-GUIDE.md](AGENT-GUIDE.md) for
Codex, Claude Code, and local module invocation patterns.

Local model use is not part of this pipeline: it sends no scene data to a model
or external service. An agent or local module can decide what to do with the
result without coupling that decision to Blender.

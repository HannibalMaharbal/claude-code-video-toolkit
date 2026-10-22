# Agent and local module integration

This is the shared Blender boundary for Claude Code, Codex, and local modules.
All agents call the same Blender script; none needs a separate add-on or Python
package. Run commands from the video-toolkit root so project-relative paths are
stable. Blender writes only into the requested output directory and refuses to
overwrite timestamped outputs.

## Standard invocation

```sh
blender -b --gpu-backend metal --python-exit-code 1 -noaudio \
  -P tools/blender_cli/run_pipeline.py -- \
  --input /absolute/path/to/model.glb \
  --output-dir projects/blender-prototype \
  --frames 72 --fps 24 --width 1280 --height 720 --save-scene
```

The input formats currently accepted are `.blend`, `.fbx`, `.glb`, `.gltf`,
`.obj`, `.stl`, and Meshy `.zip` archives containing exactly one GLB. ZIP import
streams that GLB into a temporary file without extracting archive paths; it
rejects encrypted archives, archives with zero or multiple GLBs, suspicious
compression ratios, and GLBs larger than 1 GiB. The six standalone formats
have passed local synthetic-cube import-to-MP4 smoke tests under Blender 5.2.2;
the Meshy ZIP path should be verified with an actual downloaded Meshy archive.
These tests confirm basic interchange support, not every application's
material, rig, animation, modifier, or large-file behavior. The CLI completes
import, scene preparation and validation, frame rendering, H.264 MP4 encoding,
and optional `.blend` scene export.

## Result contract

Success is exit code `0` and one stdout line prefixed `PIPELINE_RESULT ` whose
remainder is JSON (`schema_version: 1`, `status: "ok"`). It includes source,
import count, validation messages, render settings, frames directory, MP4 path,
and optional scene path. `SCENE_OK`, `RENDER_OK`, `EXPORT_OK`, and
`SCENE_EXPORT_OK` are human-readable progress lines; consumers should parse the
final JSON line instead of scraping those lines.

Pipeline failure is a nonzero exit and one stderr line prefixed
`PIPELINE_ERROR ` with JSON fields `schema_version`, `status: "error"`,
`error_type`, and `message`. Do not retry automatically: correct the input or
environment and make a new invocation. Command-line syntax errors are reported
by argparse with a nonzero exit code.

## Calling from a local Python module

```python
import json
import subprocess
from pathlib import Path

command = [
    "blender", "-b", "--gpu-backend", "metal", "--python-exit-code", "1", "-noaudio",
    "-P", "tools/blender_cli/run_pipeline.py", "--",
    "--input", "/absolute/path/to/model.obj",
    "--output-dir", "projects/blender-prototype",
    "--frames", "1", "--fps", "24", "--width", "320", "--height", "320",
]
proc = subprocess.run(command, cwd=Path.home() / "PROJEKTE/video-toolkit",
                      text=True, capture_output=True, check=False)
if proc.returncode:
    error_line = next((line for line in proc.stderr.splitlines()
                       if line.startswith("PIPELINE_ERROR ")), None)
    raise RuntimeError(error_line or proc.stderr or f"Blender exit {proc.returncode}")
result_line = next(line for line in proc.stdout.splitlines()
                   if line.startswith("PIPELINE_RESULT "))
result = json.loads(result_line.removeprefix("PIPELINE_RESULT "))
print(result["video"])
```

For another machine or checkout, set `cwd` to that checkout's root. Prefer
absolute input paths and keep generated data in ignored `projects/` locations.
To process Meshy output, download a GLB or a ZIP containing one GLB and pass
that file as `--input`; the online DCC Bridge plug-in is not required.

## Claude Code and Codex

Both can use the same shell invocation above and parse `PIPELINE_RESULT`. Keep
the input asset and expected output location in the task request; inspect the
result JSON and verify the reported MP4 exists before passing it to another
tool. Do not send confidential scene data to hosted models. Blender itself does
not call any model, network service, or external API.

## Local model modules

Local modules should invoke Blender as a subprocess using the same argument
array and consume the result contract. They may then inspect or transform the
generated file using their own local interfaces. Avoid importing Blender's
`bpy` into a model process: Blender owns its bundled Python runtime and scene
state. On this Mac, `--gpu-backend metal` is required for the tested headless
startup path.

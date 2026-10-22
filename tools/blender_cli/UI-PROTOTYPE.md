# Blender UI prototype

## Setup

The Blender 5.2 add-on uses only Blender's bundled Python API. Before setup,
`projects/blender-prototype/backups/blender-5.2/20260929-2125/` contains copies
of the existing Blender preferences and platform support file with SHA-256
checksums. No `startup.blend` existed at the time of backup. The setup refuses
to replace an existing add-on or startup file.

Run from the toolkit root:

```sh
sh tools/blender_cli/install_addon.sh
```

The script adds a symlink to the new add-on in Blender's user add-ons directory,
enables it, saves preferences, and creates Blender's `startup.blend` from the
compact `Video Studio` workspace. Restore preferences by copying the backup's
`userpref.blend` back to `~/Library/Application Support/Blender/5.2/config/`;
remove the new startup file and add-on symlink to undo setup.

## Current setup status (2026-09-29)

The project add-on symlink exists, its Blender preference is enabled, and
`startup.blend` opens the `Video Studio` workspace. The pre-change preferences
and the generated startup file have verified SHA-256 backups. Blender 5.2.2 has
passed headless import/render/export smoke tests for `.blend`, `.fbx`, `.glb`,
`.gltf`, `.obj`, `.stl`, and a Meshy-style ZIP containing one GLB. The Blender
UI operators have also passed the full Meshy ZIP → check → render → MP4 + `.blend`
save flow. The tests use synthetic geometry; check production-specific rigs,
materials, animation, and large assets individually.

## Workspace and defaults

`Video Studio` keeps the 3D View, Outliner, Properties, and timeline editors.
The add-on's **Toolkit** sidebar has clear actions to load an asset, check the
scene, render PNG frames, export an MP4, and save a `.blend` copy. Defaults are
metric meters, EEVEE, 1280×720, 24 fps, 72 frames, and the toolkit's ignored
`projects/blender-prototype/` output folder. Dated output names avoid replacing
existing clips or scenes.

## Meshy → Blender → Video Toolkit

1. In Meshy, download the finished model as `.glb` (preferred) or a ZIP archive
   containing one `.glb`. Meshy generation/download still uses the user's
   Meshy account and service.
2. In Blender's **Video Studio** workspace, open the `N` sidebar and the
   **Toolkit** tab. Click **Asset laden (GLB / ZIP / 3D)** and select the
   downloaded file. The separate Meshy Bridge add-on is not needed.
3. Set output folder, width, height, FPS, and frame count; click **Szene prüfen**.
4. Click **Frames rendern**, then **MP4 exportieren**. Optionally click
   **Szene als .blend sichern** to keep an editable scene copy.
5. Blender writes uniquely named results under the selected output directory;
   the default lives under `projects/blender-prototype/`.

Meshy ZIP import requires exactly one GLB and streams it into a temporary file
without unpacking archive paths. Encrypted ZIPs, suspicious compression ratios,
or GLBs over 1 GiB are rejected. The downloaded Meshy bridge add-on is not
installed or enabled because a source review of that package reported an
unauthenticated import bridge listening on all network interfaces. Meshy's own
docs describe the intended local bridge on port 5324; the direct file workflow
avoids running that server.

## Same pipeline from the command line

```sh
blender -b --gpu-backend metal --python-exit-code 1 -noaudio \
  -P tools/blender_cli/run_pipeline.py -- \
  --input /path/to/product.glb \
  --output-dir projects/blender-prototype \
  --frames 72 --fps 24 --width 1280 --height 720 --save-scene
```

Supported inputs are `.blend`, `.fbx`, `.glb`, `.gltf`, `.obj`, `.stl`, and
single-GLB ZIP archives. Blender writes a dated PNG sequence, then local FFmpeg
assembles a dated MP4. The script prints progress lines and a machine-readable
`PIPELINE_RESULT` JSON line for agent-driven runs. It does not invoke a model
or network service. See [AGENT-GUIDE.md](AGENT-GUIDE.md) for the shared Claude
Code, Codex, and local-module contract.

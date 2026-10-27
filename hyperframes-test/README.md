# Licbarska Consult · HyperFrames B2B Motion PoC

Deterministic 15-second HTML/CSS motion graphic rendered locally with HyperFrames.
The project is self-contained: GSAP, fonts and active sound effects live under
`assets/` and the CLI is pinned to `0.8.189`.

## Reproduce

```bash
npm run check:strict
npm run review
npm run render:delivery
npm run verify:render
# or all technical delivery gates in one pass:
npm run release:local
```

Expected delivery: 1920×1080, 30 fps, 450 frames, exactly 15 seconds, H.264 video
and 48 kHz stereo AAC. The final audio mix is independently measured after render.
Delivery filenames are allocated monotonically (`delivery`, `delivery-v2`, ...),
so reruns never overwrite an existing artifact. `verify:render` automatically
selects the newest delivery unless an explicit path is passed.

## Structure

- `index.html` — master timeline and audio mix
- `compositions/` — opening, evidence, closing and gold-wipe scenes
- `assets/` — local fonts, GSAP and semantic SFX files
- `scripts/verify-render.mjs` — deterministic ffprobe acceptance gate
- `renders/` — versioned outputs; existing files are never overwritten
- `REVIEW.md` — current visual and technical acceptance record

Publishing is intentionally not part of the scripts.

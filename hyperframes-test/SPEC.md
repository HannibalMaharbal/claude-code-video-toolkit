# HYPERFRAMES-POC-01

- 15.0 seconds, 1920×1080, 30 fps.
- Licbarska palette: navy `#0A1628`, gold `#C9A96E`, cream `#F5F0E8`.
- 0–5 s: consulting proposition; 5–10 s: single 82% demonstration counter; 10–15 s: brand end card.
- Motion: seekable GSAP only; one directional wipe, continuous progress draw, no loops or wall-clock state.
- Audio: three local bundled SFX, picture-synchronised at 5.0 s and 10.0 s; target -16 to -14 LUFS, true peak at or below -1 dBTP, no clipping.
- Offline runtime: GSAP, fonts and all active audio resolve from local `assets/`; no runtime CDN dependency.
- Delivery gate: strict HyperFrames check, review snapshots without Gemini description, 1080p H.264/AAC render and deterministic ffprobe validation.
- Non-goals: voiceover, captions, external footage, publishing, cloud rendering, integration into the existing Remotion pipeline.

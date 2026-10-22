# CODE-TO-VIDEO ARCHITEKTUR & LEITFADEN

Dokumentiert die Erstellung von Videos als deterministischer Code (HTML5/Canvas/SVG/GSAP ➔ Headless Chrome ➔ FFmpeg) zur Vermeidung von KI-Diffusions-Artefakten.

---

## 1. Das Kernprinzip

Herkömmliche Video-Diffusionsmodelle verzerren Text und geometrische Formen.
Beim **Code-to-Video**-Ansatz schreibt der Agent (Claude Code / Antigravity) die Szene vollständig als Programmcode:

```
[Agent Prompt] 
   └── Schreibt HTML5 / CSS3 / SVG / Canvas / GSAP
         │
[Headless Chrome / Puppeteer]
   └── Rendert jeden Frame deterministisch und pixelgenau
         │
[FFmpeg]
   └── Fügt Frames & Audio zu einem gestochen scharfen MP4 zusammen (bis 4K 60fps)
```

---

## 2. Die 7 verifizierten Open-Source-Referenzen

1. **`lemo-opuscar` (51 Kunst- & Filmstile):**
   * Stile: Aquarell, Holzschnitt, Tuschezeichnung, isometrische Stadt, Satelliten-Briefing.
   * Ablauf: Fragt Format, Thema, Musik ab ➔ generiert 15–45s fertige Szenen.
2. **`mg-styles-15` (15 Motion Graphics Templates):**
   * Cyberpunk, 80s Synthwave, Pixel Art, animierte Charts, vertikale 9:16 Social Media Reels.
   * Enthält integrierte 2nd-AI-Review-Rubrik zur Rhythmus- und Timing-Prüfung.
3. **`awesome-opus5-5-videos` & `opus-video-prompts`:**
   * 750+ erprobte Prompts für Pitch-Videos, Kinetische Typografie und Erklärfilme.
4. **`ClaudeAnimationBase`:**
   * Starter-Kit für Erklärfilme mit Zeichentrick-Mascot (31 Mimik- und Gesten-Zustände).
5. **`awesome-claude-5-5-videos`:**
   * Benchmarks und Kostenvergleiche (Haiku für Prototyping, Sonnet/Opus für komplexe 3D-Canvas-Szenen).

---

## 3. Einsatzbereiche im HANNIBAL AI OS

* **Ideal für:** Kinetische Typografie, Social Media Reels, UI-Showcases, Erklärvideos, animierte Diagramme und Produkt-Intros mit 100% scharfem Text.
* **Nicht für:** Fotorealistische menschliche Darsteller (hierfür bleibt die Standard-Pipeline: LTX 2.5 lokal, MiniMax H3, Veo 3.1 oder Seedance).

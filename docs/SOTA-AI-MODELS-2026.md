# SOTA AI Model & Pipeline Playbook (2026 Edition)

> **Kanonische Referenz für HANNIBAL AI OS & Video-Toolkit**  
> Basierend auf den verifizierten Praxis-Benchmarks und Architektur-Tests (ZELDOgiq SOTA-Reihe).

---

## 1. Lokale Video-Generierung: MiniMax H3 & LTX-2.5

Für lokale, grenzkostenfreie Videoerstellung (0 € Grenzkosten) stehen zwei primäre Architekturen zur Verfügung, die direkt auf Consumer-Hardware bzw. Apple Silicon laufen.

### 1.1 VRAM-Skalierung & Modellvarianten
| Modell | Ziel-Hardware / VRAM | Setup / Toolchain | Stärke / Einsatzbereich |
|---|---|---|---|
| **LTX-2.5 MLX** | Apple Silicon (M-Serie Unified Memory) | `tools/ltx25_mlx_adapter.py` / `ltx-2-mlx` | Tier-1 Drafts, 0 € Scrap-Filter, Motion- & Timing-Preflight |
| **LTX-2.5 (PC)** | 8 GB VRAM (RTX 3060/4060) | Pinokio ➔ Maestro AI | Schnelle lokale Entwürfe, 24 fps nativ |
| **MiniMax H3 Distilled** | 8 GB VRAM | Pinokio ➔ Maestro AI | UGC-Kurzclips (5s), extrem geringer Speicherbedarf |
| **MiniMax H3 Pruned** | 10 GB VRAM | Pinokio ➔ Maestro AI | Solider Kompromiss aus Bewegungsschärfe und VRAM |
| **MiniMax H3 Dev / Full** | 12–16 GB VRAM (RTX 4070+) | Pinokio ➔ Maestro AI | Maximale Detailtreue, komplexe Beleuchtung |

### 1.2 Character-Lock via H3 Omni Referenzmodus
* **Problem:** Gesichts- und Kleidungsdrift bei fortlaufenden Videoszenen.
* **Lösung:** H3 Omni erlaubt Multi-Referenz-Bilder (Frontal, Profil, Mimik).
* **Praxis-Workflow:**
  1. Key-Visual / Character-Sheet in Nano Banana 2.1 oder GPT Image 3 generieren.
  2. Bis zu 3 Referenzbilder in Maestro / H3 Omni einspeisen.
  3. Image-to-Video mit Startframe verriegeln.
  4. End-Frame für Folgeclips extrahieren (Kanonisches End-Frame = Start-Frame Gesetz).

### 1.3 LTX-2.5 Kinematische Trajektorien: DEV vs. Distilled Motion Profiling
Aus verifizierten Stresstests (identische End-Anchors, 121 Frames @ 24 fps, 1920×1088, RTX 5090) folgt: **Endpunkt-Konvergenz ist kein Beweis für Bewegungsqualität.**
* **DEV-Pfad (40 Steps, CFG 3.5, W4A8 ConvRot):**
  * *Stärke:* Hält lokale Workspaces und Feinkontakt (z. B. Hände, Werkzeuge, Tischflächen) ruhiger und mit weniger Raumdrift.
  * *Einsatz:* Interaktionsszenen, Dialoge, statischere Einstellungen mit feinen Mikro-Gesten.
* **Distilled-Pfad (Fixed Schedule / 8–12 Steps, CFG 1.0, INT8):**
  * *Stärke:* Überlegene Re-Identifikation und Kontinuität nach Vordergrund-Okklusionen (z. B. Passanten kreuzen das Bild).
  * *Einsatz:* Belebte Straßen- und Marktszenen, dynamische Durchquerungen.
* **Kritische Schwachstelle beider Pfade:** Dynamisches Objekt-Binding (z. B. getragene Gegenstände wie Rettungsringe oder Taschen verändern Griff und Position). Hier sind kürzere Schnittintervalle oder Inpainting-Korrekturen zwingend.

### 1.4 LTX-2.5 SDR-to-HDR IC-LoRA Pipeline (ACEScg & 10-Bit HLG Master)
Generative In-Context LoRA Rekonstruktion zur verlustfreien Überführung von 8-Bit SDR-Material in echte 10-Bit HDR-Master:
* **Workflow:** `ComfyUI-LTXVideo` Stage 1 (`LTX-2.5_V2V_TiledFusion_SDR_to_HDR`).
* **Basis:** LTX-2.5 Distilled Transformer (bf16, SageAttention, 8 Distilled Steps, CFG 1.0, LoRA Stärke 1.0).
* **Dynamikumfang:** ACEScg Scene-Linear Luminanz erreicht im 99.9. Perzentil 4.5 bis 15.8 (Peaks bis 55.0; normales SDR clippt starr bei 1.0). 1–6 % der Bildpunkte im HDR-Highlightbereich (kein Ausbrennen von Scheinwerfern/Reflexionen; Schatten behalten Karbon- und Materialtexturen).
* **Anti-Banding-Vorschrift:**
  * `use_tiled_encode`: **OFF** (verhindert reproduzierbare vertikale Streifen/Banding in Tiefen).
  * `streaming encode`: **ON** (97-Frame Temporal Windows).
* **Mastering:** Export als ACEScg Half-Float EXR-Sequenz oder HLG BT.2020 10-Bit Master zur nahtlosen Übergabe an das DaVinci Resolve Finishing Gate.

---

## 2. Lokale Bildretusche & Inpainting: Qwen Image 2.1 & Fibo 2.0

### 2.1 Qwen Image 2.1 (7B Open Source)
* **Hardware:** Läuft lokal und offline auf 12 GB VRAM (z. B. RTX 4070).
* **Installation:** Pinokio ➔ Wan2GP ➔ Maestro AI.
* **Leistung & Benchmarks:**
  * Schlägt Krea 2 bei Realismus und Text-in-Image Rendering.
  * Inpainting und selektive Bildbearbeitung auf Augenhöhe mit GPT Image 2.5.
  * Nativ optimiert für Englisch und Chinesisch (Deutsch noch fehleranfällig).
* **Einsatz:** Kostenfreie Freisteller, Hintergrundwechsel, Outfit-Wechsel und Textkorrekturen im Bild ohne API-Kosten.

### 2.2 Fibo 2.0
* Lokales Open-Source-Modell als Alternative zu Cloud-Inpainting.
* Beseitigt Cloud-Abhängigkeiten bei sensiblen Assets.

---

## 3. Cloud Visuals & Charakter-Konsistenz: Nano Banana 2.1 & GPT Image 3

### 3.1 Nano Banana 2.1
* **Plattform:** Google Flow (kostenlos).
* **Kernvorteil:** Übertrifft GPT Image 2.5 bei Gesichts- und Kleidungskonsistenz deutlich.
* **Einsatzbereich:** Primäre Quelle für konsistente Key-Visuals, Model-Sheets und Storyboard-Vorlagen.

### 3.2 GPT Image 3 (OpenAI Leak / LM Arena)
* **Status:** Vorabtest via LM Arena (`aurora red`, `aurora blue`, `aurora green alpha`).
* **Physik-Treue:** Weinglas-Test bestanden (korrekte Brechung, Lichtreflexion und Flüssigkeitsdynamik ohne Artefakte).
* **Rendering:** Beseitigung des früheren Blauschimmers und der Wölkchen-Artefakte.
* **Character-Sheet-Generierung:** Extraktion eines 360°-Character-Sheets aus einem einzigen Frontalfoto.

---

## 4. Reasoning & Prompt-Engineering: Gemini 4 Argon

### 4.1 Effizienz & Coding
* ~80 % Kostenersparnis gegenüber GPT-6 Astra und Claude Fable 5.1.
* Hochgradig fähig bei Frontend-Animationen (z. B. komplexe Scroll-Effekte im Apple-Stil) und präzisen SVG-Generierungen („Panda auf dem Fahrrad“).

### 4.2 Seedance 2 Mini Prompt-Optimierung
* **Ziel:** High-End-Videoqualität (nahe Seedance 2.5) bei **10-fach geringeren Generierungskosten** über Seedance 2 Mini.
* **Prompt-Strukturierungsformel:**
  1. **Kameraführung:** Explizite Nennung von Brennweite und Bewegung (z. B. `35mm lens, slow cinematic dolly push-in, shallow depth of field, f/1.8`).
  2. **Beleuchtung & Atmosphäre:** Feste Farbtemperatur und Lichtquelle (z. B. `golden hour warm rim lighting, soft volumetric haze`).
  3. **Physik & Mikro-Gesten:** Kein starres Motiv (z. B. `subtle micro-expressions, gentle natural breathing, realistic eye blink, fabric rustling in gentle breeze`).
  4. **Kader & Details:** Genaue Texturbeschreibungen vermeiden generischen KI-Look.

### 4.3 Medienanalyse & Video-Reverse-Engineering
* Gemini 4 Argon dekonstruiert Referenz-Videoclips Bild für Bild und extrahiert daraus den vollständigen Regie- und Ausführungsprompt für Replizierung im gewünschten Modell.

---

## 5. Audio, Stimmklonen & Mastering: Gemini 3.8 Flash TTS & Suno v6

### 5.1 Gemini 3.8 Flash TTS
* **Tool im Toolkit:** `tools/gemini_tts.py`
* **Voice Cloning:** 30 Sekunden Audiomaterial in Google AI Studio genügen für einen sauberen Klon.
* **Die 5 Produktions-Modi (`--mode`):**
  * `friendly`: Warmer, sympathischer Konversationston.
  * `narration`: Dokumentarischer, klarer Erzählstil mit gemessenem Pacing.
  * `promote`: Energischer, werblicher Pitch für Social UGC und Ads.
  * `podcast`: Dynamischer, lockerer Dialogstil (Co-Host).
  * `whisper`: Sanfter, intimer Flüsterton für Spannung oder ASMR.
* **Integrierte Expression-Tags (direkt im Text einbettbar):**
  * `[laugh]` – natürliches Lachen
  * `[sigh]` – Seufzen
  * `[breath]` – Atemholen
  * `[whisper]` – Flüsterelement
  * `[pause]` – gezielte Sprechpause

### 5.2 Suno v6 (Studiomusik & Mastering)
* **Entwicklung:** Kooperation mit **Warner Music** und **BMG**.
* **Audioqualität:** Professionelle Dynamik, saubere Transienten, echter Studio-Mastering-Standard (keine muffigen Höhen oder Hall-Artefakte wie in v4/v5).
* **Echte Duett-Funktion:**
  * Klare Stimmtrennung zwischen zwei Charakteren (z. B. Banana Girl & Boss Panda).
  * Strukturierung im Prompt:
    ```text
    [Verse 1: Female Lead, soft acoustic guitar]
    ...
    [Verse 2: Male Rapper, punchy 808 beat]
    ...
    [Chorus: Both in Duet, rich vocal harmony]
    ...
    ```

---

## 6. Matrix: Dispatching im HANNIBAL AI OS

| Anforderung | Empfohlenes Werkzeug | Fallback |
|---|---|---|
| **Lokales Video (0 € Grenzkosten)** | LTX-2.5 MLX (Mac) / MiniMax H3 (PC 8–12 GB) | LTX-2.5 via ComfyUI/Maestro |
| **Cloud Video (Standard T2V)** | Wan 3.0 via `video_generate.py` | MiniMax H3 |
| **Cloud Video (Low-Cost Character)** | Seedance 2 Mini (mit Argon-Prompting) | Wan 3.0 |
| **Cloud Video (High-End & Soul-Lock)** | Seedance 2.5 via Higgsfield | Wan 3.0 Prime |
| **Charakter-Sheet & Key-Visual** | Nano Banana 2.1 / GPT Image 3 | GPT Image 2.5 |
| **Lokale Bildretusche & Text-in-Image** | Qwen Image 2.1 (12 GB VRAM) | Fibo 2.0 |
| **Voiceover / Dubbing** | Gemini 3.8 Flash TTS (`gemini_tts.py`) | Kokoro TTS / Piper (lokal) |
| **Musik & Werbe-Jingles** | Suno v6 (Warner/BMG Master) | ACE-Step 1.5 (`music_gen.py`) |

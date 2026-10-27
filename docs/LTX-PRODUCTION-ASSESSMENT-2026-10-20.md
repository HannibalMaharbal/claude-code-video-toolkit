# LTX für kontrollierte lokale Videoproduktion

## M4 Pro mit 24 GB: kalibrierte lokale Profile

Der zentrale Dispatcher bietet zwei Distilled-Q8-Profile. `HERO` ist der
qualitätsorientierte Default; `STANDARD` bleibt die schnellere Option. Längere Sequenzen werden bevorzugt aus kurzen, per Endframe
fortgesetzten Shots aufgebaut.

```bash
# Schnellere Produktion: 768×448
uv run tools/video_generate.py --local-profile STANDARD --prompt "..." --output standard.mp4

# Qualitätsorientierter Default: 1024×576
uv run tools/video_generate.py --local-profile HERO --prompt "..." --output hero.mp4
```

Beide Profile verwenden lokal Distilled Q8, Low-RAM und genau einen
abschließenden VideoToolbox-CAS-Pass. Der STANDARD-Rohcanvas wird dabei nach
einem minimalen zentrierten 16:9-Beschnitt exakt auf 1920×1080 ausgegeben;
profilabhängiges CAS (STANDARD 0,45, HERO 0,35) vermeidet die Halos der früheren
globalen Stärke 0,6. HERO verbessert Details, ist auf diesem
Host aber deutlich langsamer; es ist kein anderer Transformer und kein Ersatz
für den offiziellen DFR-Produktionspfad.

Stand: 20. Oktober 2026

## Produktionsrelevante Stärken

LTX passt grundsätzlich zur lokalen HANNIBAL-Architektur: Die offiziellen
Lightricks-Repositories stellen Modellcode und Gewichte für lokale Inferenz
bereit. Dadurch können vertrauliche Produktions-Assets im lokalen Pfad bleiben
und ein Cloud-Anbieter ist nicht für jeden Generationslauf erforderlich.

Der offizielle LTX-2-Stack unterstützt außerdem Standard-LoRAs und einen
Trainer. IC-LoRAs lernen Transformationen aus gepaarten Referenz- und
Zielvideos, etwa für Depth-, Pose- oder Canny-Steuerung, Stiltransfer,
Restaurierung und Inpainting. Diese Fähigkeiten sind für wiederkehrende
Charaktere, Sets und kontrollierte VFX langfristig relevant.

Generatives Material wird trotzdem nicht automatisch zum Final Master. Der
richtige Produktionspfad bleibt:

1. LTX für Previsualisierung, Shot-Entwicklung und generative Plates,
2. Kontinuitäts- und Artefaktprüfung,
3. Compositing, Schnitt und Farbkorrektur,
4. finales DaVinci-Resolve-/Fairlight-Gate.

## Tatsächlich aktiver lokaler Stand

Der installierte Pfad verwendet `tools/ltx25_mlx_adapter.py` mit dem gepinnten
MLX-Runtime-Stand `57952288` und lokal vorhandenen quantisierten
LTX-2.5-Gewichten. Er bietet Text-to-Video, Image-to-Video, synchronisierte
Audio-/Video-Ausgabe sowie Mehrclip-Fortsetzung über `--continue-from`.

Die Mehrclip-Fortsetzung verwendet das dekodierte letzte Frame des vorherigen
Clips als verlustfreien PNG-Anker. Das verbessert die visuelle Kontinuität,
garantiert aber keine identische erste Ausgabeframe und ersetzt keine
Abnahme von Identität, Kleidung, Requisiten, Raum, Licht und Bewegung.

Der auf diesem M4 Pro mit 24 GB live belegte Referenzlauf benötigte für 97
Frames ungefähr 191 Sekunden. Der lokale Pfad ist daher iterativ nutzbar,
aber nicht als Echtzeit-Generierung zu bezeichnen.

## Neu belegte optionale VFX-Fähigkeiten

Lightricks dokumentiert inzwischen zwei getrennte IC-LoRA-Workflows:

- **Layout to Render (Beta):** Ein 3D-Blocking- oder Referenzvideo führt
  Kamera, Komposition und Frame-Ausrichtung während der Generierung.
- **Alpha Gen (Beta):** Die offizielle
  `LTX-2.5-22b-IC-LoRA-Alpha-Gen` verarbeitet ein RGB-Video und erzeugt eine
  gleich lange, framegenau ausgerichtete Graustufen-Alpha-Matte. Diese Matte
  wird anschließend beim Compositing als Alpha-Kanal des RGB-Clips verwendet.

Alpha Gen ist damit eine reale LTX-VFX-Fähigkeit, aber **kein nativer
Transparenzkanal jedes normalen LTX-Renders**. Es handelt sich um einen
separaten Video-to-Video-IC-LoRA-Lauf. Laut offizieller Model Card gilt er für
höchstens 145 Frames und bis 1920×1088; die Auswahl des Vordergrundobjekts ist
nicht per Prompt oder Maske steuerbar.

Der vorhandene MLX-Runtime-Quellstand besitzt grundsätzlich einen IC-LoRA-Pfad
und LoRA-Fusion. Die konkreten LTX-2.5-Modelle für Alpha Gen und Layout to
Render sind jedoch nicht lokal vorhanden oder mit diesem gepinnten Stand live
verifiziert. Alpha Gen ist außerdem zugangsbeschränkt: Vor einem Download sind
Hugging-Face-Anmeldung, Lizenzprüfung, Datennutzungsprüfung, Speicherprüfung
und ausdrückliche Aktivierungsfreigabe erforderlich.

Der aktuelle MLX-IC-LoRA-Pfad ist zudem als zweistufige Pipeline ausgelegt;
`--skip-stage-2` liefert laut lokaler CLI nur eine halbaufgelöste Ausgabe.
Alpha Gen verlangt dagegen eine framegleich ausgerichtete Matte aus einem
nativen Stage-1-Lauf. Deshalb wird die vorhandene generische IC-LoRA-CLI nicht
ungeprüft als Alpha-Gen-Adapter verwendet. Vor Aktivierung müssen Auflösung,
Framezahl und Zeitstempel des RGB-Eingangs und der erzeugten Matte exakt
gegeneinander geprüft werden.

## Nicht als aktive Fähigkeit behaupten

- **Eigenes LoRA-/IC-LoRA-Training:** upstream verfügbar, in diesem lokalen
  MLX-Pfad aber weder installiert noch live verifiziert. Training ist eine
  separate Pipeline mit eigenem Dataset-, Hardware-, Lizenz- und Review-Gate.
- **Alpha im normalen Renderpfad:** Der aktive MP4-Adapter erzeugt keine
  Alpha-Matte. Die belegte Alpha-Funktion ist ein separates, derzeit nicht
  installiertes IC-LoRA-V2V-Modul.
- **Kino- oder sendefertiger Output:** Weder Open Weights noch ein Upsampler
  garantieren Final-Pixel-Qualität. Jeder Shot bleibt prüf- und
  postproduktionspflichtig.
- **Echtzeit auf dem vorhandenen Mac:** durch den gemessenen lokalen Lauf
  widerlegt. Aussagen über Echtzeit sind hardware- und pipelineabhängig.
- **Asteria-Pilotfilm als Systemnachweis:** Der beschriebene Film und dessen
  konkrete Produktionsdetails wurden in den geprüften offiziellen Quellen
  nicht bestätigt und werden deshalb nicht als kanonischer Nachweis geführt.

## Übernommene Leitentscheidung

LTX bleibt das lokale offene Arbeitspferd für kontrollierte Iteration und
zusammenhängende Clips. Layout to Render und Alpha Gen sind sinnvolle nächste
VFX-Kandidaten, bleiben aber getrennte, erst nach Lizenz-, Ressourcen- und
Live-Test aktivierbare Module. LoRA-Training und zusätzliche Upscaling-Pfade
unterliegen demselben Gate.
Marketingaussagen werden nicht mit dem nachgewiesenen Betriebsstatus
vermischt.

Die Registry führt beide Kandidaten deshalb sichtbar, aber nicht routbar:
Layout to Render als `planned`, Alpha Gen als `blocked`. Der aktive
Produktionspfad bleibt der lokale MLX-Adapter für Previsualisierung, I2V und
Mehrclip-Fortsetzung mit anschließendem DaVinci-Gate.

## Primärquellen

- Offizielles LTX-Repository: <https://github.com/Lightricks/LTX-Video>
- Offizielle LTX-VFX-Lösung: <https://ltx.io/solution/vfx>
- Offizielle Alpha-Gen-Model-Card:
  <https://huggingface.co/Lightricks/LTX-2.5-22b-IC-LoRA-Alpha-Gen>
- Offizieller LTX-2-Stack und Trainer: <https://github.com/Lightricks/LTX-2>
- Offizielle Trainingsmodi und IC-LoRA-Dokumentation:
  <https://github.com/Lightricks/LTX-Video-Trainer/blob/main/docs/training-modes.md>
- Offizielle Dataset-Vorbereitung:
  <https://github.com/Lightricks/LTX-Video-Trainer/blob/main/docs/dataset-preparation.md>

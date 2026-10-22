---
name: voiceover
description: Adding locally generated voiceover to Remotion compositions
metadata:
  tags: voiceover, audio, local-tts, speech, calculateMetadata, dynamic duration
---

# Adding local voiceover to a Remotion composition

Generate narration as local audio files with the toolkit's Kokoro or Piper
provider. For a cloned voice, use local Qwen3-TTS only after the model is
installed and the speaker has given explicit consent. Do not add cloud voice
providers or API keys to the production path.

```bash
uv run tools/voiceover.py --scene-dir public/audio/scenes --provider kokoro --json
```

Use [`calculateMetadata`](./calculate-metadata.md) to measure audio durations
and set the composition length accordingly.

```tsx
import { CalculateMetadataFunction, staticFile } from "remotion";
import { getAudioDuration } from "./get-audio-duration";

const FPS = 30;
const SCENE_AUDIO_FILES = [
  "voiceover/my-comp/scene-01-intro.mp3",
  "voiceover/my-comp/scene-02-main.mp3",
];

export const calculateMetadata: CalculateMetadataFunction<Props> = async () => {
  const durations = await Promise.all(
    SCENE_AUDIO_FILES.map((file) => getAudioDuration(staticFile(file))),
  );
  const totalDurationInSeconds = durations.reduce((sum, duration) => sum + duration, 0);
  return { durationInFrames: Math.ceil(totalDurationInSeconds * FPS) };
};
```

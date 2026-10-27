import { createHash } from "node:crypto";
import { readFileSync, readdirSync } from "node:fs";
import { execFileSync } from "node:child_process";

const versions = readdirSync("renders")
  .map((name) => {
    const match = name.match(/^licbarska-consult-b2b-delivery(?:-v(\d+))?-15s\.mp4$/);
    return match ? { name, version: Number(match[1] ?? 1) } : null;
  })
  .filter(Boolean)
  .sort((a, b) => b.version - a.version);
const file = process.argv[2] ?? (versions[0] && `renders/${versions[0].name}`);
if (!file) throw new Error("No delivery render found; run npm run render:delivery first");

const probe = JSON.parse(execFileSync("ffprobe", [
  "-v", "error",
  "-count_frames",
  "-show_entries", "format=duration,size:stream=codec_type,codec_name,width,height,avg_frame_rate,nb_read_frames,sample_rate,channels",
  "-of", "json",
  file,
], { encoding: "utf8" }));

const video = probe.streams.find((stream) => stream.codec_type === "video");
const audio = probe.streams.find((stream) => stream.codec_type === "audio");
const failures = [];

if (probe.format.duration !== "15.000000") failures.push(`duration=${probe.format.duration}`);
if (!video || video.codec_name !== "h264") failures.push(`videoCodec=${video?.codec_name}`);
if (video?.width !== 1920 || video?.height !== 1080) failures.push(`dimensions=${video?.width}x${video?.height}`);
if (video?.avg_frame_rate !== "30/1") failures.push(`fps=${video?.avg_frame_rate}`);
if (video?.nb_read_frames !== "450") failures.push(`frames=${video?.nb_read_frames}`);
if (!audio || audio.codec_name !== "aac") failures.push(`audioCodec=${audio?.codec_name}`);
if (audio?.sample_rate !== "48000" || audio?.channels !== 2) failures.push(`audio=${audio?.sample_rate}Hz/${audio?.channels}ch`);

if (failures.length) {
  console.error(`FAIL ${file}: ${failures.join(", ")}`);
  process.exit(1);
}

const sha256 = createHash("sha256").update(readFileSync(file)).digest("hex");
console.log(JSON.stringify({
  ok: true,
  file,
  sha256,
  bytes: Number(probe.format.size),
  durationSeconds: 15,
  video: "h264 1920x1080 30fps 450frames",
  audio: "aac 48000Hz stereo",
}));

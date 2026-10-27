import { existsSync } from "node:fs";
import { spawnSync } from "node:child_process";

const stem = "renders/licbarska-consult-b2b-delivery";
let version = 1;
let output = `${stem}-15s.mp4`;
while (existsSync(output)) {
  version += 1;
  output = `${stem}-v${version}-15s.mp4`;
}

console.log(`Rendering version-safe delivery: ${output}`);
const result = spawnSync("npx", [
  "--yes",
  "hyperframes@0.8.189",
  "render",
  "--quality", "delivery",
  "--strict-all",
  "--output", output,
], { stdio: "inherit" });

if (result.error) throw result.error;
process.exit(result.status ?? 1);

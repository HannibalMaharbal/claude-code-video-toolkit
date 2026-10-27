import { execFileSync } from "node:child_process";

const output = execFileSync("npx", [
  "--yes",
  "hyperframes@0.8.189",
  "check",
  "--json",
], { encoding: "utf8" });

const report = JSON.parse(output.slice(output.indexOf("{")));
const sections = ["lint", "runtime", "layout", "motion", "contrast", "craft"];
const failures = sections.flatMap((name) => {
  const section = report[name];
  if (!section) return [`${name}=missing`];
  const errors = section.errorCount ?? 0;
  const warnings = section.warningCount ?? 0;
  return errors || warnings ? [`${name}=${errors} errors/${warnings} warnings`] : [];
});

if (!report.ok || failures.length) {
  console.error(`FAIL HyperFrames strict check: ${failures.join(", ") || "report.ok=false"}`);
  process.exit(1);
}

console.log(JSON.stringify({
  ok: true,
  version: report._meta?.version,
  durationSeconds: report.layout?.duration,
  contrast: `${report.contrast?.passed}/${report.contrast?.checked}`,
  filesScanned: report.lint?.filesScanned,
  errors: 0,
  warnings: 0,
}));

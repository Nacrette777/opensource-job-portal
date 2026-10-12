// Read-only compatibility check against the sibling RR checkout's actual UI importer.
// Run with that checkout's tsx loader (see docs/gradbridge-resume-export.md).
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { parseArgs } from "node:util";

const { values } = parseArgs({
  options: { "rr-root": { type: "string" }, input: { type: "string" } },
});
if (!values["rr-root"] || !values.input) {
  throw new Error("Required: --rr-root <Reactive Resume directory> --input <JSON Resume file>");
}
const rrRoot = path.resolve(values["rr-root"]);
const rrImport = (relative) => import(pathToFileURL(path.join(rrRoot, relative)).href);
const { detectJsonImportType } = await rrImport("apps/web/src/dialogs/resume/import.utils.ts");
const { parseResumeJson } = await rrImport("apps/web/src/dialogs/resume/parse-json.ts");
const text = await readFile(values.input, "utf8");
const source = JSON.parse(text);
assert.equal(detectJsonImportType(source), "json-resume-json");
// parseResumeJson calls parseJSONResume, which validates the final resumeDataSchema.
const native = parseResumeJson(text, "json-resume-json");
for (const key of ["name", "email", "phone"]) {
  assert.ok(native.basics[key] === (source.basics[key] || ""), `${key}: mapping changed`);
}
assert.ok(native.basics.headline === (source.basics.label || ""), "headline: mapping changed");
const mapping = { education: "education", work: "experience", skills: "skills", projects: "projects" };
const counts = {};
for (const [standard, rrSection] of Object.entries(mapping)) {
  counts[standard] = native.sections[rrSection].items.length;
  assert.equal(counts[standard], (source[standard] || []).length, `${standard}: RR dropped an entry`);
}
for (const [index, project] of (source.projects || []).entries()) {
  const description = native.sections.projects.items[index].description;
  for (const highlight of project.highlights || []) assert.ok(description.includes(highlight));
}
// Never print personal data or save RR-native output.
console.log(JSON.stringify({ format: "json-resume-json", accepted: true, counts }));

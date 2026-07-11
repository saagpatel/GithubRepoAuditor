/* Golden runner: replays every Python-generated case through the JS port and
 * diffs exact equality. Run with:  node run_golden.cjs   (from this directory) */
"use strict";

const fs = require("fs");
const path = require("path");

const core = require("../verdict_core.js");
const goldens = JSON.parse(fs.readFileSync(path.join(__dirname, "goldens.json"), "utf8"));

function deepEqual(a, b) {
  return JSON.stringify(a) === JSON.stringify(b);
}

const failures = [];
let total = 0;

function check(section, index, input, expected, actual) {
  total += 1;
  if (!deepEqual(expected, actual)) {
    failures.push({ section, index, input, expected, actual });
  }
}

for (const [i, c] of goldens.activity.entries()) {
  const status = core.activityStatusFor(c.input);
  check("activity", i, c.input, c.expected, status);
  check("registry", i, c.input, c.expected_registry, core.registryStatusFor(status));
}

for (const [i, c] of goldens.context.entries()) {
  check("context", i, c.input, c.expected, core.contextQualityFor(c.input));
}

for (const [i, c] of goldens.pathing.entries()) {
  const r = core.buildOperatingPathEntry(c.input.entry, c.input.options);
  const projected = {
    operating_path: r.operating_path,
    operating_path_source: r.operating_path_source,
    path_override: r.path_override,
    path_confidence: r.path_confidence,
    path_rationale: r.path_rationale,
  };
  check("pathing", i, c.input, c.expected, projected);
}

for (const [i, c] of goldens.risk.entries()) {
  check("risk", i, c.input, c.expected, core.buildRiskEntry(c.input));
}

for (const [i, c] of goldens.attention.entries()) {
  check("attention", i, c.input, c.expected, core.attentionStateFor(c.input));
}

const bySection = {};
for (const f of failures) bySection[f.section] = (bySection[f.section] || 0) + 1;

console.log(`golden cases: ${total}`);
console.log(`failures: ${failures.length}`);
if (failures.length) {
  console.log("failures by section:", JSON.stringify(bySection));
  for (const f of failures.slice(0, 5)) {
    console.log("---");
    console.log("section:", f.section, "case:", f.index);
    console.log("input:   ", JSON.stringify(f.input));
    console.log("expected:", JSON.stringify(f.expected));
    console.log("actual:  ", JSON.stringify(f.actual));
  }
  process.exit(1);
}
console.log("ALL GOLDENS PASS — JS port matches the Python source exactly.");

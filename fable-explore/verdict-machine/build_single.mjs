// Builds the self-contained single-file artifact: inlines verdict_core.js into
// index.html and writes dist/verdict-machine.html.
// Run: node build_single.mjs   (from this directory)
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const html = readFileSync(join(here, "index.html"), "utf8");
const core = readFileSync(join(here, "verdict_core.js"), "utf8");

const tag = '<script src="verdict_core.js"></script>';
if (!html.includes(tag)) {
  console.error("marker script tag not found in index.html");
  process.exit(1);
}
const out = html.replace(tag, `<script>\n${core}\n</script>`);

mkdirSync(join(here, "dist"), { recursive: true });
const outPath = join(here, "dist", "verdict-machine.html");
writeFileSync(outPath, out);
console.log(`wrote ${outPath} (${(out.length / 1024).toFixed(1)} KB)`);

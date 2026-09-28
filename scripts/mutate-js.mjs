// Plant deliberate breaks in a scratch copy of Matinee's page scripts and report which JavaScript test
// caught each one. Usage: `node scripts/mutate-js.mjs MUTATIONS.json`, run from the repository root.
// MUTATIONS.json is a list of `[id, file, search, replace, condition]`: `search` is replaced by
// `replace` in `file` (relative to the repository) and must occur, or the run stops with an error
// rather than running a break that changed nothing. The static scripts, the stylesheet and tests/js
// are copied to a directory under the system's temporary directory, so the real tree is never
// touched; each copy is removed after its run. The unmutated tests must all pass first.
import { execFileSync } from "node:child_process";
import { cpSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const PARTS = ["src/matinee/web/static/js", "src/matinee/web/static/css", "tests/js", "package.json"];
const TESTS = "tests/js/*.test.mjs";

const listing = process.argv[2];
if (!listing) throw new Error("usage: node scripts/mutate-js.mjs MUTATIONS.json");
const mutations = JSON.parse(readFileSync(listing, "utf8"));

// The names of the tests that failed, or none.
function failures(dir) {
  try {
    execFileSync("node", ["--test", "--test-reporter=tap", TESTS], { cwd: dir, stdio: "pipe" });
    return [];
  } catch (err) {
    const out = String(err.stdout);
    // A test file that fails to load reports under its own path; that counts as a catch too.
    return [...out.matchAll(/^\s*not ok \d+ - (.+)$/gm)].map((m) => m[1].trim());
  }
}

// Runs `fn` against a fresh copy of the repository's page scripts and tests, then removes the copy.
function inCopy(fn) {
  const dir = mkdtempSync(join(tmpdir(), "mutate-js-"));
  try {
    for (const part of PARTS) cpSync(part, join(dir, part), { recursive: true });
    return fn(dir);
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

const base = inCopy(failures);
if (base.length) throw new Error(`the unmutated tests fail: ${base.join("; ")}`);

const rows = mutations.map(([id, file, search, replace, condition]) =>
  inCopy((dir) => {
    const path = join(dir, file);
    const text = readFileSync(path, "utf8");
    if (!text.includes(search)) throw new Error(`${id}: search text not found in ${file}`);
    writeFileSync(path, text.replace(search, replace));
    return { id, condition, by: failures(dir) };
  }),
);

for (const r of rows) console.log(`${r.id}  ${r.by.length ? "CAUGHT  " : "SURVIVED"}  ${r.condition}${r.by.length ? `  <- ${r.by.join(" | ")}` : ""}`);
const names = readdirSync("tests/js")
  .filter((f) => f.endsWith(".test.mjs"))
  .flatMap((f) => [...readFileSync(join("tests/js", f), "utf8").matchAll(/^test\("(.+?)"/gm)].map((m) => m[1]));
console.log("\nper assertion:");
for (const name of names) console.log(`  ${rows.filter((r) => r.by.includes(name)).map((r) => r.id).join(",") || "NONE"}  <- ${name}`);
console.log(`\n${rows.filter((r) => r.by.length).length} of ${rows.length} breaks caught`);

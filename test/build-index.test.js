"use strict";

const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");
const { buildIndex } = require("../build-index.js");

const slide = (id, extra = {}) => ({
  id,
  title: `T ${id}`,
  subtitle: "s",
  steps: [{ number: 1, heading: "h", body_markdown: "b" }],
  ...extra,
});

function tmpSlides(files) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "slides-"));
  for (const [name, content] of Object.entries(files)) {
    fs.writeFileSync(path.join(dir, name), typeof content === "string" ? content : JSON.stringify(content));
  }
  return dir;
}

test("inlines single-slide files and gives them a resolvable url", () => {
  const dir = tmpSlides({ "02-b.json": slide("b"), "01-a.json": slide("a") });
  const { slides } = buildIndex({ slidesDir: dir });
  assert.deepStrictEqual(slides.map((s) => s.id), ["a", "b"]);
  assert.deepStrictEqual(slides.map((s) => s.order), [1, 2]);
  assert.strictEqual(slides[0].url, "slides/01-a.json");
  assert.ok(Array.isArray(slides[0].steps));
});

test("flattens deck files and keeps global order", () => {
  const dir = tmpSlides({ "a.json": { slides: [slide("x"), slide("y")] }, "b.json": slide("z") });
  const { slides } = buildIndex({ slidesDir: dir });
  assert.deepStrictEqual(slides.map((s) => s.id), ["x", "y", "z"]);
  assert.strictEqual(slides[0].url, undefined);
  assert.strictEqual(slides[2].order, 3);
});

test("lazy mode emits url-only for single-slide files but inlines deck slides", () => {
  const dir = tmpSlides({ "a.json": { slides: [slide("x")] }, "b.json": slide("z") });
  const { slides } = buildIndex({ slidesDir: dir, lazy: true });
  assert.ok(slides[0].steps);
  assert.strictEqual(slides[1].steps, undefined);
  assert.strictEqual(slides[1].url, "slides/b.json");
});

test("every emitted url resolves to an existing file", () => {
  const dir = tmpSlides({ "a.json": slide("a"), "b.json": slide("b") });
  for (const s of buildIndex({ slidesDir: dir, lazy: true }).slides) {
    assert.ok(fs.existsSync(path.join(dir, path.basename(s.url))));
  }
});

test("rejects invalid JSON, duplicate ids and malformed slides", () => {
  assert.throws(() => buildIndex({ slidesDir: tmpSlides({ "a.json": "{nope" }) }), /invalid JSON/);
  assert.throws(
    () => buildIndex({ slidesDir: tmpSlides({ "a.json": slide("d"), "b.json": slide("d") }) }),
    /duplicate slide id/,
  );
  assert.throws(
    () => buildIndex({ slidesDir: tmpSlides({ "a.json": { id: "q", title: "t", steps: [] } }) }),
    /non-empty/,
  );
});

test("CLI writes the output file", () => {
  const dir = tmpSlides({ "a.json": slide("a") });
  const out = path.join(dir, "..", `idx-${path.basename(dir)}.json`);
  execFileSync("node", [path.join(__dirname, "..", "build-index.js"), "--slides-dir", dir, "--out", out]);
  assert.strictEqual(JSON.parse(fs.readFileSync(out, "utf8")).slides.length, 1);
});

test("repository slides/ builds cleanly", () => {
  const { slides } = buildIndex({ slidesDir: path.join(__dirname, "..", "slides") });
  assert.ok(slides.length > 0);
});

test("--dist copies only the files a static host needs", () => {
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), "dist-"));
  const out = path.join(dist, "..", `idx2-${path.basename(dist)}.json`);
  const root = path.join(__dirname, "..");
  execFileSync("node", [path.join(root, "build-index.js"), "--out", out, "--dist", dist]);
  assert.ok(fs.existsSync(path.join(dist, "slides", "slide1.json")));
  assert.ok(fs.existsSync(path.join(dist, "index.html")));
  assert.ok(!fs.existsSync(path.join(dist, "raw_pdfs")));
  assert.deepStrictEqual(JSON.parse(fs.readFileSync(path.join(dist, "index.json"), "utf8")), JSON.parse(fs.readFileSync(out, "utf8")));
});

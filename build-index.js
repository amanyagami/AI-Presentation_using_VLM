// build-index.js
// Builds index.json from slides/*.json (the single source of truth).
//
//   node build-index.js [--lazy] [--slides-dir DIR] [--out FILE] [--dist DIR]
//
// Each slides/*.json file is either a single Slide ({id,title,subtitle,steps})
// or a Deck ({"slides":[Slide,...]}). By default every slide is inlined into
// index.json (`steps` included) and single-slide files also get a `url`.
// With --lazy, single-slide files are emitted url-only (no `steps`) and the
// viewer fetches them on demand; slides from Deck files are always inlined.
// With --dist DIR, the files a static host needs (index.html, index.json,
// slides/, extracted_data/*/images) are also copied into DIR.

"use strict";

const fs = require("fs");
const path = require("path");

function validateSlide(slide, where) {
  const fail = (msg) => {
    throw new Error(`${where}: ${msg}`);
  };
  if (!slide || typeof slide !== "object") fail("slide must be an object");
  if (typeof slide.id !== "string" || !slide.id) fail("missing string `id`");
  if (typeof slide.title !== "string") fail(`slide ${slide.id}: missing string \`title\``);
  if (!Array.isArray(slide.steps) || slide.steps.length === 0) {
    fail(`slide ${slide.id}: \`steps\` must be a non-empty array`);
  }
  slide.steps.forEach((s, i) => {
    if (!s || typeof s.heading !== "string" || typeof s.body_markdown !== "string") {
      fail(`slide ${slide.id}: step ${i + 1} needs string heading and body_markdown`);
    }
  });
}

function buildIndex({ slidesDir, lazy = false }) {
  const files = fs
    .readdirSync(slidesDir)
    .filter((f) => f.endsWith(".json"))
    .sort();

  const slides = [];
  const seen = new Set();

  for (const file of files) {
    let data;
    try {
      data = JSON.parse(fs.readFileSync(path.join(slidesDir, file), "utf8"));
    } catch (err) {
      throw new Error(`${file}: invalid JSON (${err.message})`);
    }

    const isDeck = data && Array.isArray(data.slides);
    const items = isDeck ? data.slides : [data];

    items.forEach((slide, i) => {
      validateSlide(slide, isDeck ? `${file}[${i}]` : file);
      if (seen.has(slide.id)) throw new Error(`${file}: duplicate slide id "${slide.id}"`);
      seen.add(slide.id);

      const entry = {
        id: slide.id,
        title: slide.title,
        subtitle: slide.subtitle || "",
        order: slides.length + 1,
      };
      if (!isDeck) entry.url = `slides/${file}`;
      if (isDeck || !lazy) entry.steps = slide.steps;
      slides.push(entry);
    });
  }

  return { slides };
}

function copyDist(root, dist, indexFile) {
  fs.rmSync(dist, { recursive: true, force: true });
  fs.mkdirSync(dist, { recursive: true });
  fs.copyFileSync(path.join(root, "index.html"), path.join(dist, "index.html"));
  fs.copyFileSync(indexFile, path.join(dist, "index.json"));
  fs.cpSync(path.join(root, "slides"), path.join(dist, "slides"), { recursive: true });
  const data = path.join(root, "extracted_data");
  if (fs.existsSync(data)) {
    for (const paper of fs.readdirSync(data)) {
      const imgs = path.join(data, paper, "images");
      if (fs.existsSync(imgs)) {
        fs.cpSync(imgs, path.join(dist, "extracted_data", paper, "images"), { recursive: true });
      }
    }
  }
}

function main(argv) {
  const opt = (name) => {
    const i = argv.indexOf(name);
    return i >= 0 ? argv[i + 1] : undefined;
  };
  const slidesDir = path.resolve(opt("--slides-dir") || path.join(__dirname, "slides"));
  const out = path.resolve(opt("--out") || path.join(__dirname, "index.json"));
  const index = buildIndex({ slidesDir, lazy: argv.includes("--lazy") });
  fs.writeFileSync(out, JSON.stringify(index, null, 2) + "\n");
  console.log(`index.json generated successfully (${index.slides.length} slides)`);
  const dist = opt("--dist");
  if (dist) {
    copyDist(__dirname, path.resolve(dist), out);
    console.log(`static site copied to ${dist}`);
  }
}

if (require.main === module) {
  try {
    main(process.argv.slice(2));
  } catch (err) {
    console.error(`build-index failed: ${err.message}`);
    process.exit(1);
  }
}

module.exports = { buildIndex, validateSlide, copyDist };

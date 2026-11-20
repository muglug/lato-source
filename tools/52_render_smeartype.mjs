import assert from 'node:assert/strict';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { pathToFileURL } from 'node:url';

const [source, manifestPath] = process.argv.slice(2);
const { SubpixelRenderer } = await import(pathToFileURL(resolve(source, 'src/renderer.js')));
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
const renderer = await SubpixelRenderer.create({
  wasmBinary: await readFile(resolve(source, 'vendor/freetype/freetype.wasm')),
});
assert.equal(renderer.capabilities.v40, true);
let currentFont;
for (const job of manifest.jobs) {
  if (job.font !== currentFont) {
    renderer.loadFont(await readFile(job.font));
    currentFont = job.font;
  }
  renderer.font = {
    unitsPerEm: job.upm,
    stringToGlyphs: text => {
      assert.equal(text, job.text);
      return job.glyphs;
    },
    getKerningValue: () => 0,
  };
  const result = renderer.render({
    text: job.text, width: job.width, height: job.height,
    size: job.size, x: job.margin, baseline: job.baseline,
    mode: 'lcd', axis: 'horizontal', order: 'rgb', filter: 'default',
    hinting: job.hinting, gamma: manifest.gamma, strength: 1,
    foreground: '#172332', background: '#ffffff',
  });
  assert.equal(result.glyphCount, job.glyphs.length);
  assert.equal(result.missingGlyphs, 0);
  await writeFile(job.output, result.data);
}
await writeFile(manifest.capabilities_path, JSON.stringify(renderer.capabilities, null, 2));
renderer.destroy();
console.log(`Smeartype rendered ${manifest.jobs.length} ss05 samples with exact HarfBuzz advances.`);

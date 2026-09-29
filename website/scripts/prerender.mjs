// Writes the server-rendered page into dist/index.html so the copy is in the HTML for
// crawlers, link previews and visitors without JavaScript. Run by `npm run build`.
import { readFile, rm, writeFile } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = fileURLToPath(new URL('..', import.meta.url));
const ssrDir = `${root}dist-ssr`;
const htmlPath = `${root}dist/index.html`;

const { render } = await import(pathToFileURL(`${ssrDir}/entry-server.js`).href);
const html = await readFile(htmlPath, 'utf8');
const marker = '<div id="root"></div>';
if (!html.includes(marker)) throw new Error(`prerender: ${marker} not found in dist/index.html`);

await writeFile(htmlPath, html.replace(marker, `<div id="root">${render()}</div>`));
await rm(ssrDir, { recursive: true, force: true });
console.log('prerender: wrote dist/index.html');

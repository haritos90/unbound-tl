import { readFile } from "node:fs/promises";

const root = process.env.GEN3TL_WEB_ROOT_URL;

const { patchEngine } = await import(new URL("js/patch-engine.js", root));

const wasm = new URL("js/patcher/rom-patcher.wasm", root).href;

const fetcher = globalThis.fetch;

// Node's fetch rejects file URLs.
try {
  globalThis.fetch = async (url, options) => url.href === wasm ? new Response(await readFile(url)) : fetcher(url, options);
  await patchEngine();
} finally {
  globalThis.fetch = fetcher;
}

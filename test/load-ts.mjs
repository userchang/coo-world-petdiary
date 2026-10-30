/** 用 esbuild 把单个 TS 入口 bundle 成临时 ESM，供 node:test 直接 import。 */
import { mkdir, mkdtemp, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';

const buildRoot = fileURLToPath(new URL('../.p4-build', import.meta.url));

export async function loadTs(entry, cacheKey = entry) {
  await mkdir(buildRoot, { recursive: true });
  const dir = await mkdtemp(join(buildRoot, 'test-'));
  const outfile = join(dir, 'bundle.mjs');
  try {
    await build({
      entryPoints: [entry],
      outfile,
      bundle: true,
      format: 'esm',
      platform: 'node',
      target: 'node22',
      logLevel: 'silent',
      sourcemap: false,
    });
    return await import(`${pathToFileURL(outfile).href}?v=${encodeURIComponent(cacheKey)}`);
  } finally {
    await rm(dir, { recursive: true, force: true }).catch(() => {});
  }
}

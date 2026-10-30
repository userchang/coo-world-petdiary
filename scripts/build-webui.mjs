#!/usr/bin/env node
/**
 * 把 src/panels/*.ts bundle 成 ESM 单文件 dist/webui.js，并把 import 的 CSS
 * 输出到 dist/webui.css。浏览器端产物不包含任何 cortico/* 运行时 import。
 */
import { mkdir, rm } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { build } from 'esbuild';

const packageRoot = fileURLToPath(new URL('..', import.meta.url));
const dist = fileURLToPath(new URL('../dist', import.meta.url));

// 只清前端产物；dist/ 里不再保留任何含真实日记的静态快照。
await mkdir(dist, { recursive: true });
await rm(new URL('../dist/webui.js', import.meta.url), { force: true });
await rm(new URL('../dist/webui.css', import.meta.url), { force: true });

const result = await build({
  absWorkingDir: packageRoot,
  entryPoints: ['src/panels/diary.ts'],
  outfile: 'dist/webui.js',
  bundle: true,
  format: 'esm',
  platform: 'browser',
  target: 'es2022',
  sourcemap: false,
  minify: false,
  legalComments: 'none',
  logLevel: 'info',
});

if (result.errors.length) {
  process.exitCode = 1;
} else {
  console.log('webui 构建完成：dist/webui.js + dist/webui.css');
}

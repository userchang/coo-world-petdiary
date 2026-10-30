#!/usr/bin/env node
/** 开发辅助：从 definition.ts 的 DESCRIBE 生成 describe.json（发布前跑一次）。 */
import { mkdir, mkdtemp, rm, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';

const packageRoot = fileURLToPath(new URL('..', import.meta.url));
// Windows 的 %TEMP% 可能被 ACL 锁住；构建临时文件放包内，.gitignore 已忽略。
const buildRoot = join(packageRoot, '.p4-build');
await mkdir(buildRoot, { recursive: true });
const dir = await mkdtemp(join(buildRoot, 'describe-'));
const bundleFile = join(dir, 'definition.mjs');
try {
  await build({
    entryPoints: [join(packageRoot, 'src', 'definition.ts')],
    outfile: bundleFile,
    bundle: true,
    platform: 'node',
    format: 'esm',
    target: 'node22',
    logLevel: 'silent',
  });
  const { DESCRIBE } = await import(pathToFileURL(bundleFile).href);
  await writeFile(join(packageRoot, 'describe.json'), `${JSON.stringify(DESCRIBE, null, 2)}\n`, 'utf8');
  console.log('已生成 describe.json');
} finally {
  await rm(dir, { recursive: true, force: true }).catch(() => {});
}

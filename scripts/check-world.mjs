#!/usr/bin/env node
/**
 * 用 Cortico 自己的 parseExtensionManifest / dryMountWorld 跑一遍装配自检。
 *
 * 框架源码是 .ts，`node --experimental-strip-types` 跑不了 parameter property；
 * 这里用 esbuild 把「我们的入口 + 框架检查函数」bundle 成临时 ESM 再 import，
 * 不复制任何检查逻辑。框架路径按 CORTICO_SRC / --cortico-src / 相对默认值查找。
 */
import { copyFile, mkdtemp, readFile, rm, writeFile, mkdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { build } from 'esbuild';

const packageRoot = fileURLToPath(new URL('..', import.meta.url));
const distJs = join(packageRoot, 'dist', 'webui.js');
const distCss = join(packageRoot, 'dist', 'webui.css');

function argValue(name) {
  const index = process.argv.indexOf(name);
  return index >= 0 ? process.argv[index + 1] : undefined;
}

function findCorticoSrc() {
  const explicit = argValue('--cortico-src') || process.env.CORTICO_SRC;
  if (explicit) return resolve(explicit);
  // 默认只在仓库旁 / 依赖里找；其他位置用 CORTICO_SRC 或 --cortico-src 显式指定。
  const candidates = [
    new URL('../cortico/src', import.meta.url),
    new URL('../node_modules/cortico/src', import.meta.url),
    new URL('../../cortico/src', import.meta.url),
  ];
  for (const candidate of candidates) {
    const path = fileURLToPath(candidate);
    if (existsSync(join(path, 'extensions', 'dry-mount.ts'))) return path;
  }
  return fileURLToPath(candidates[0]);
}

async function main() {
  const pkg = JSON.parse(await readFile(join(packageRoot, 'package.json'), 'utf8'));
  const corticoSrc = findCorticoSrc();
  const dryMountFile = join(corticoSrc, 'extensions', 'dry-mount.ts');
  const manifestFile = join(corticoSrc, 'extensions', 'manifest.ts');
  if (!existsSync(dryMountFile) || !existsSync(manifestFile)) {
    throw new Error(`找不到 Cortico 源码：${corticoSrc}（用 CORTICO_SRC 或 --cortico-src 指定）`);
  }
  if (!existsSync(distJs)) throw new Error(`缺少 ${distJs}；先跑 node scripts/build-webui.mjs`);
  if (!existsSync(distCss)) throw new Error(`缺少 ${distCss}；CSS import 没有产出`);

  const buildRoot = join(packageRoot, '.p4-build');
  await mkdir(buildRoot, { recursive: true });
  const scratch = await mkdtemp(join(buildRoot, 'drymount-'));
  const entryFile = join(scratch, 'check-entry.ts');
  const bundleFile = join(scratch, 'check-entry.mjs');
  try {
    await mkdir(join(scratch, 'deployment'), { recursive: true });
    // import.meta.url 在 bundle 后变成临时目录；把模板放到它旁边，检查才和真机一致。
    await copyFile(join(packageRoot, 'src', 'ENV_PROMPT.md'), join(scratch, 'ENV_PROMPT.md'));
    const entry = `
import pkg from ${JSON.stringify(join(packageRoot, 'package.json'))};
import { parseExtensionManifest } from ${JSON.stringify(manifestFile)};
import { dryMountWorld } from ${JSON.stringify(dryMountFile)};
import definition from ${JSON.stringify(join(packageRoot, 'src', 'index.ts'))};
const manifestResult = parseExtensionManifest(pkg, 'zh');
const report = await dryMountWorld(definition, {
  scratchDir: ${JSON.stringify(scratch)},
  packageDir: ${JSON.stringify(packageRoot)},
  repoRoot: ${JSON.stringify(packageRoot)},
  language: 'zh',
  hasWebUiClient: true,
});
const toolInfo = (definition.describe?.tools ?? []).map((tool) => ({
  name: tool.name,
  length: (tool.description ?? '').length,
}));
export default { manifestResult, report, toolInfo };
`;
    await writeFile(entryFile, entry, 'utf8');
    await build({
      entryPoints: [entryFile],
      outfile: bundleFile,
      bundle: true,
      platform: 'node',
      format: 'esm',
      target: 'node22',
      logLevel: 'silent',
      sourcemap: false,
    });
    const checked = await import(pathToFileURL(bundleFile).href);
    const { manifestResult, report, toolInfo } = checked.default;

    const failures = [...report.failures];
    if (!manifestResult.ok) failures.unshift(...manifestResult.reasons);
    const warnings = [...(manifestResult.warnings ?? []), ...report.warnings];

    console.log('manifest：');
    if (manifestResult.ok) {
      console.log(`  ok — kind=${manifestResult.manifest.kind} api=${manifestResult.manifest.api} displayName=${manifestResult.manifest.displayName ?? ''}`);
    } else {
      console.log('  failed');
    }
    console.log(`  webUiClient=${pkg.cortico?.webUiClient ?? ''}（${existsSync(distJs) ? '存在' : '缺失'}）`);
    console.log(`  webUiStyle=${pkg.cortico?.webUiStyle ?? ''}（${existsSync(distCss) ? '存在' : '缺失'}）`);
    console.log('');

    console.log('工具描述长度：');
    for (const tool of toolInfo) console.log(`  - ${tool.name}: ${tool.length} 字`);
    console.log(`  合计：${toolInfo.reduce((sum, tool) => sum + tool.length, 0)} 字`);
    console.log('');

    console.log('ok：');
    for (const line of report.ok) console.log(`  - ${line}`);
    if (!report.ok.length) console.log('  （无）');
    console.log('');
    console.log('warnings：');
    for (const line of warnings) console.log(`  - ${line}`);
    if (!warnings.length) console.log('  （无）');
    console.log('');
    console.log('failures：');
    for (const line of failures) console.log(`  - ${line}`);
    if (!failures.length) console.log('  （无）');
    console.log('');
    console.log(`dryMountWorld: ${failures.length === 0 ? 'PASS' : 'FAIL'} (${report.ok.length} ok / ${warnings.length} warnings / ${failures.length} failures)`);
    if (failures.length) process.exitCode = 1;
  } finally {
    await rm(scratch, { recursive: true, force: true }).catch(() => {});
  }
}

main().catch((error) => {
  console.error(`check-world 失败：${error instanceof Error ? error.message : String(error)}`);
  process.exitCode = 1;
});

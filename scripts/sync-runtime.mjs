#!/usr/bin/env node
/**
 * 把开发用的 diary 后端脚本同步到插件自带的 runtime/diary/。
 *
 * 插件发布后不再依赖外部 agdiary 目录；脚本改动先改 agdiary，再跑这里
 * （`npm run build` 的 prebuild 会自动跑一次）。发布包不包含 scripts/，
 * 所以这个开发辅助脚本不会进入 npm 包。
 *
 * 默认从同级的 ../../agdiary/diary 取；也可用 PETDIARY_BACKEND 指定源目录。
 */
import { cp, rm } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { basename, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const source = process.env.PETDIARY_BACKEND
  ? resolve(process.env.PETDIARY_BACKEND)
  : fileURLToPath(new URL('../../agdiary/diary', import.meta.url));
const target = fileURLToPath(new URL('../runtime/diary', import.meta.url));

if (!existsSync(source)) {
  throw new Error(`找不到 diary 后端源码：${source}（用 PETDIARY_BACKEND 指定）`);
}

await rm(target, { recursive: true, force: true });
await cp(source, target, {
  recursive: true,
  filter: (path) => {
    const name = basename(path).toLowerCase();
    if (['__pycache__', '.pytest_cache', '.tmp', 'test', 'tests'].includes(name)) return false;
    if (name.endsWith('.pyc') || name.endsWith('.log')) return false;
    return true;
  },
});
console.log(`runtime/diary 同步完成：${source} -> ${target}`);

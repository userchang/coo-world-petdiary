/**
 * 插件自带的默认值推导。只做纯路径计算 + 存在性检查，不写配置、不建库。
 *
 * 安装后目录固定为 `<Coo>/data/extensions/node_modules/<包名>/`，
 * 因此从插件目录向上一级到 node_modules，再向上两级即 data：
 *   <插件>/runtime/python/python.exe
 *   <插件>/runtime/diary/
 *   <data>/home/companion/workspace/petdiary/
 */
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import type { PetDiarySection } from './config.ts';

export interface PetDiaryDefaults {
  packageDir: string;
  dataDir: string;
  /** 内置解释器存在时的绝对路径；否则为空，走 PATH 回退。 */
  pythonPath: string;
  /** 内置 diary 脚本存在时的绝对路径；否则为空，走库根同级 diary/ 回退。 */
  scriptsDir: string;
  /** 默认库根；目录不存在时由 bridge 在首次使用时初始化。 */
  libraryRoot: string;
  bundledPython: boolean;
  bundledScripts: boolean;
}

export interface AppliedDefaults {
  cfg: PetDiarySection;
  defaults: PetDiaryDefaults;
  /** 哪些字段实际用了自动默认（用于决定是否允许自动初始化默认库）。 */
  usedDefaults: {
    libraryRoot: boolean;
    pythonPath: boolean;
    scriptsDir: boolean;
  };
}

/** 本模块所在包目录（src/..）；打包成临时 bundle 时也可由调用方传入 packageDir。 */
export function modulePackageDir(): string {
  return resolve(dirname(fileURLToPath(import.meta.url)), '..');
}

/**
 * 推导默认值。`dataDir` 优先由调用方从 botDir（data/home/companion）反推，
 * 否则按插件目录向上三级（node_modules → extensions → data）计算。
 */
export function resolveDefaults(packageDir = modulePackageDir(), dataDir?: string): PetDiaryDefaults {
  const pkg = resolve(packageDir);
  const data = dataDir ? resolve(dataDir) : resolve(pkg, '..', '..', '..');
  const python = join(pkg, 'runtime', 'python', 'python.exe');
  const scripts = join(pkg, 'runtime', 'diary');
  const bundledPython = process.platform === 'win32' && existsSync(python);
  const bundledScripts = existsSync(join(scripts, 'admin.py'));
  return {
    packageDir: pkg,
    dataDir: data,
    pythonPath: bundledPython ? python : '',
    scriptsDir: bundledScripts ? scripts : '',
    libraryRoot: join(data, 'home', 'companion', 'workspace', 'petdiary'),
    bundledPython,
    bundledScripts,
  };
}

/** 用户显式配置 > 自动默认 > 现有回退链；不修改传入的 cfg，也不写回 config.json。 */
export function applyDefaults(
  cfg: PetDiarySection,
  defaults: PetDiaryDefaults = resolveDefaults(),
): AppliedDefaults {
  const libraryRoot = cfg.libraryRoot.trim();
  const pythonPath = cfg.pythonPath.trim();
  const scriptsDir = cfg.scriptsDir.trim();
  return {
    cfg: {
      ...cfg,
      libraryRoot: libraryRoot || defaults.libraryRoot,
      pythonPath: pythonPath || defaults.pythonPath,
      scriptsDir: scriptsDir || defaults.scriptsDir,
    },
    defaults,
    usedDefaults: {
      libraryRoot: !libraryRoot,
      pythonPath: !pythonPath && Boolean(defaults.pythonPath),
      scriptsDir: !scriptsDir && Boolean(defaults.scriptsDir),
    },
  };
}

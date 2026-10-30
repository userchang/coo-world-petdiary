import assert from 'node:assert/strict';
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { loadTs } from './load-ts.mjs';

const here = (name) => fileURLToPath(new URL(name, import.meta.url));
const defaultsMod = await loadTs(here('../src/defaults.ts'), 'defaults');
const bridge = await loadTs(here('../src/bridge.ts'), 'bridge');

const emptyCfg = {
  enabled: false,
  libraryRoot: '',
  pythonPath: '',
  scriptsDir: '',
  bedtimeCheck: '23:59',
};

async function tempDir(name) {
  return mkdtemp(join(tmpdir(), `petdiary-${name}-`));
}

test('defaults resolve bundled runtime and data-root library', async () => {
  const pkg = await tempDir('pkg');
  const data = await tempDir('data');
  try {
    await mkdir(join(pkg, 'runtime', 'python'), { recursive: true });
    await writeFile(join(pkg, 'runtime', 'python', 'python.exe'), 'dummy');
    await mkdir(join(pkg, 'runtime', 'diary'), { recursive: true });
    await writeFile(join(pkg, 'runtime', 'diary', 'admin.py'), '# dummy');
    const resolved = defaultsMod.resolveDefaults(pkg, data);
    assert.equal(resolved.packageDir, pkg);
    assert.equal(resolved.dataDir, data);
    assert.equal(resolved.pythonPath, join(pkg, 'runtime', 'python', 'python.exe'));
    assert.equal(resolved.scriptsDir, join(pkg, 'runtime', 'diary'));
    assert.equal(
      resolved.libraryRoot,
      join(data, 'home', 'companion', 'workspace', 'petdiary'),
    );
    assert.equal(resolved.bundledPython, true);
    assert.equal(resolved.bundledScripts, true);
  } finally {
    await rm(pkg, { recursive: true, force: true });
    await rm(data, { recursive: true, force: true });
  }
});

test('defaults fall back to empty python/scripts when runtime is absent', async () => {
  const pkg = await tempDir('pkg-empty');
  const data = await tempDir('data-empty');
  try {
    const resolved = defaultsMod.resolveDefaults(pkg, data);
    assert.equal(resolved.pythonPath, '');
    assert.equal(resolved.scriptsDir, '');
    assert.equal(resolved.bundledPython, false);
    assert.equal(resolved.bundledScripts, false);
    assert.equal(
      resolved.libraryRoot,
      join(data, 'home', 'companion', 'workspace', 'petdiary'),
    );
  } finally {
    await rm(pkg, { recursive: true, force: true });
    await rm(data, { recursive: true, force: true });
  }
});

test('explicit config always wins over defaults', async () => {
  const pkg = await tempDir('pkg-apply');
  const data = await tempDir('data-apply');
  try {
    const resolved = defaultsMod.resolveDefaults(pkg, data);
    const explicitRoot = join(data, 'explicit-lib');
    const explicitPython = join(data, 'explicit-python.exe');
    const explicitScripts = join(data, 'explicit-diary');
    const applied = defaultsMod.applyDefaults({
      ...emptyCfg,
      libraryRoot: explicitRoot,
      pythonPath: explicitPython,
      scriptsDir: explicitScripts,
    }, resolved);
    assert.equal(applied.cfg.libraryRoot, explicitRoot);
    assert.equal(applied.cfg.pythonPath, explicitPython);
    assert.equal(applied.cfg.scriptsDir, explicitScripts);
    assert.deepEqual(applied.usedDefaults, {
      libraryRoot: false,
      pythonPath: false,
      scriptsDir: false,
    });

    const empty = defaultsMod.applyDefaults(emptyCfg, resolved);
    assert.equal(empty.cfg.libraryRoot, resolved.libraryRoot);
    assert.equal(empty.usedDefaults.libraryRoot, true);
  } finally {
    await rm(pkg, { recursive: true, force: true });
    await rm(data, { recursive: true, force: true });
  }
});

test('runAdmin initializes the default library once and is idempotent', async () => {
  const root = await tempDir('default-lib');
  const data = await tempDir('default-data');
  const pkg = await tempDir('default-pkg');
  const scripts = await tempDir('default-scripts');
  const initLog = join(root, 'init.log');
  const fakeAdmin = `
const fs = require('node:fs');
const path = require('node:path');
const command = process.argv[2];
const root = process.argv[process.argv.indexOf('--root') + 1];
if (command === 'init') {
  fs.mkdirSync(root, { recursive: true });
  fs.writeFileSync(path.join(root, 'index.diary'), 'index');
  fs.appendFileSync(${JSON.stringify(initLog)}, 'init\\n');
  process.stdout.write('已建库\\n');
} else if (command === 'state') {
  process.stdout.write(JSON.stringify({
    ok: true,
    state: { library: { name: '默认库', mode: 'single' }, counts: {}, entries: [] },
  }) + '\\n');
} else {
  process.stdout.write(JSON.stringify({ ok: true }) + '\\n');
}
`;
  await writeFile(join(scripts, 'admin.py'), fakeAdmin, 'utf8');
  const defaults = {
    packageDir: pkg,
    dataDir: data,
    pythonPath: '',
    scriptsDir: scripts,
    libraryRoot: root,
    bundledPython: false,
    bundledScripts: true,
  };
  const logs = [];
  try {
    const first = await bridge.runAdmin(emptyCfg, 'state', [], {
      defaults,
      pythonCandidates: [process.execPath],
      log: (message) => logs.push(message),
    });
    assert.equal(first.ok, true, JSON.stringify(first));
    assert.equal(existsSync(join(root, 'index.diary')), true);
    assert.equal((await readFile(initLog, 'utf8')).trim().split(/\r?\n/).length, 1);
    assert.ok(logs.some((line) => line.includes('已初始化默认日记库')));

    const second = await bridge.runAdmin(emptyCfg, 'state', [], {
      defaults,
      pythonCandidates: [process.execPath],
      log: (message) => logs.push(message),
    });
    assert.equal(second.ok, true);
    assert.equal((await readFile(initLog, 'utf8')).trim().split(/\r?\n/).length, 1);
  } finally {
    await rm(root, { recursive: true, force: true });
    await rm(data, { recursive: true, force: true });
    await rm(pkg, { recursive: true, force: true });
    await rm(scripts, { recursive: true, force: true });
  }
});

test('world defaults survive real host ctx: botDir doubling + packageDir being deploy dir', async () => {
  // 回归 P5.7 现场两个坑：
  // 1) ctx.botDir = <data>/home/companion，dirname 只到 <data>/home，
  //    再拼 home/companion/... 会得到 data/home/home/...；
  // 2) ctx.packageDir 是 bot 部署目录（没有 runtime/），必须探测模块自身位置。
  const worldModule2 = await loadTs(here('../src/world.ts'), 'world-defaults-ctx');
  const data = await mkdtemp(join(tmpdir(), 'petdiary-ctx-data-'));
  const deploy = join(data, 'home', 'companion');
  try {
    // 伪造一个"真实安装目录"（含 runtime/diary），模拟生产里 import.meta.url 指向的位置；
    // 测试 bundle 在 .p4-build 下，modulePackageDir() 指不到它，所以用 moduleDir 注入。
    const pkg = join(data, 'extensions', 'node_modules', 'coo-world-petdiary');
    await mkdir(join(pkg, 'runtime', 'diary'), { recursive: true });
    await writeFile(join(pkg, 'runtime', 'diary', 'admin.py'), '# fake backend\n', 'utf8');
    const world = new worldModule2.PetDiaryWorld({
      cfg: { enabled: true, libraryRoot: '', pythonPath: '', scriptsDir: '', bedtimeCheck: '23:59' },
      packageDir: deploy, // 模拟宿主：部署目录冒充 packageDir
      botDir: deploy,
      moduleDir: pkg,
      timezone: 'Asia/Shanghai',
    });
    const applied = world.defaults();
    // botDir 兜底路径：data/home/companion 上两级 = data，库根不再翻倍
    assert.equal(
      applied.libraryRoot,
      join(data, 'home', 'companion', 'workspace', 'petdiary'),
    );
    // 部署目录没有 runtime → 回退模块自身位置，仓库里 runtime/diary 真实存在
    assert.equal(applied.bundledScripts, true);
    assert.ok(applied.scriptsDir.endsWith(join('runtime', 'diary')), applied.scriptsDir);
  } finally {
    await rm(data, { recursive: true, force: true });
  }
});

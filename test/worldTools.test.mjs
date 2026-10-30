// P5.7 回归：handler 级测试。0.3.0~0.3.2 的 admin(cli) 漏传子命令
// 只有在真实调用 world.tools() handler 时才会暴露，单测全是绕过这层的。
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { mkdtemp, mkdir, rm } from 'node:fs/promises';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { loadTs } from './load-ts.mjs';

const here = (name) => fileURLToPath(new URL(name, import.meta.url));
const worldModule = await loadTs(here('../src/world.ts'), 'world-tools');

const runtimePython = join(repoRoot(), 'runtime', 'python', 'python.exe');
const runtimeAdmin = join(repoRoot(), 'runtime', 'diary', 'admin.py');
function repoRoot() {
  return fileURLToPath(new URL('..', import.meta.url));
}
const hasRuntime = existsSync(runtimePython) && existsSync(runtimeAdmin);

test('diary_append / diary_read handlers write and read end-to-end', { skip: !hasRuntime && '需要内置 runtime' }, async () => {
  const base = join(repoRoot(), 'test', '.tmp');
  await mkdir(base, { recursive: true });
  const root = await mkdtemp(join(base, 'tools-'));
  execFileSync(runtimePython, [runtimeAdmin, 'init', '--root', root, '--name', '测试库'], { stdio: 'pipe' });
  try {
    const world = new worldModule.PetDiaryWorld({
      cfg: { enabled: true, libraryRoot: root, pythonPath: runtimePython, scriptsDir: join(repoRoot(), 'runtime', 'diary'), bedtimeCheck: '23:59' },
      packageDir: 'D://nonexistent-deploy-dir',
      botDir: root,
      timezone: 'Asia/Shanghai',
    });
    const append = world.tools().find((t) => t.name === 'diary_append');
    const read = world.tools().find((t) => t.name === 'diary_read');

    const out = await append.handler({
      book: 'private', time: '01:30', title: 'handler 回归', body: '第一段。\n\n第二段。', kind: '心情',
    });
    assert.equal(out.failed, undefined, JSON.stringify(out));
    assert.match(String(out.text), /已写入|记下了|private/);

    const listing = await read.handler({ scope: 'all' });
    assert.equal(listing.failed, undefined, JSON.stringify(listing));
    assert.match(String(listing.text), /handler 回归/);
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

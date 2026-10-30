import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { loadTs } from './load-ts.mjs';

const here = (name) => fileURLToPath(new URL(name, import.meta.url));
const bridge = await loadTs(here('../src/bridge.ts'), 'bridge');

function cfg(root, scripts, extra = {}) {
  return {
    enabled: false,
    libraryRoot: root,
    pythonPath: process.execPath,
    scriptsDir: scripts,
    ...extra,
  };
}

async function fakeAdmin(body) {
  const dir = await mkdtemp(join(tmpdir(), 'petdiary-admin-'));
  await writeFile(join(dir, 'admin.py'), body, 'utf8');
  return dir;
}

test('parseAdminJson takes the last JSON line', () => {
  assert.deepEqual(
    bridge.parseAdminJson('log line\n{"ok":true,"value":1}\n'),
    { ok: true, value: 1 },
  );
  assert.equal(bridge.parseAdminJson('not json'), null);
  assert.equal(bridge.parseAdminJson('[1,2]'), null);
});

test('resolveScriptsDir explains missing admin.py', () => {
  const result = bridge.resolveScriptsDir(cfg('', ''));
  assert.equal(result.ok, false);
  assert.match(result.error, /库根/);

  const missing = bridge.resolveScriptsDir(cfg('placeholder-lib', ''));
  assert.equal(missing.ok, false);
  assert.match(missing.error, /admin\.py/);
});

test('success returns parsed data', async () => {
  const dir = await fakeAdmin('process.stdout.write(JSON.stringify({ok:true,value:7})+"\\n");');
  try {
    const result = await bridge.runAdmin(cfg(dir, dir), 'read', ['--limit', '1']);
    assert.equal(result.ok, true);
    assert.equal(result.data.value, 7);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('exit code 1 keeps error and hint', async () => {
  const dir = await fakeAdmin(
    'process.stdout.write(JSON.stringify({ok:false,error:"数据有问题",hint:"看条目 x"})+"\\n");process.exit(1);',
  );
  try {
    const result = await bridge.runAdmin(cfg(dir, dir), 'append');
    assert.equal(result.ok, false);
    assert.equal(result.code, 1);
    assert.equal(result.error, '数据有问题');
    assert.equal(result.hint, '看条目 x');
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('exit code 2 maps to parameter/root problem', async () => {
  const dir = await fakeAdmin('process.exit(2);');
  try {
    const result = await bridge.runAdmin(cfg(dir, dir), 'append');
    assert.equal(result.ok, false);
    assert.equal(result.code, 2);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('invalid JSON on exit 0 is a human error', async () => {
  const dir = await fakeAdmin('process.stdout.write("不是 JSON\\n");');
  try {
    const result = await bridge.runAdmin(cfg(dir, dir), 'state');
    assert.equal(result.ok, false);
    assert.equal(result.code, 5);
    assert.match(result.error, /没有返回 JSON/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('timeout maps to a human timeout message', async () => {
  const dir = await fakeAdmin('setTimeout(() => {}, 5000);');
  try {
    const result = await bridge.runAdmin(cfg(dir, dir), 'state', [], { timeoutMs: 120 });
    assert.equal(result.ok, false);
    assert.equal(result.code, 3);
    assert.match(result.error, /超时/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

test('missing Python reports pythonPath hint', async () => {
  const dir = await fakeAdmin('process.stdout.write("{}\\n");');
  try {
    const result = await bridge.runAdmin(cfg(dir, dir, { pythonPath: 'definitely-no-such-python-petdiary' }), 'state');
    assert.equal(result.ok, false);
    assert.equal(result.code, 4);
    assert.match(result.hint, /pythonPath/);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

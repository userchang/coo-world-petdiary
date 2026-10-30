import assert from 'node:assert/strict';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { loadTs } from './load-ts.mjs';

const here = (name) => fileURLToPath(new URL(name, import.meta.url));
const integrity = await loadTs(here('../src/integrity.ts'), 'integrity');
const i18n = await loadTs(here('../src/i18n.ts'), 'i18n');
const worldMod = await loadTs(here('../src/world.ts'), 'world');

const zh = i18n.text('zh');

function cfg(root, pythonPath = process.execPath) {
  return {
    enabled: true,
    libraryRoot: root,
    pythonPath,
    scriptsDir: root,
  };
}

/** 假 admin.py（用 node 执行）：commands 记到 calls.log，verify/delete 按参数返回。 */
async function fakeAdmin({ verify, state, deleteJson } = {}) {
  const dir = await mkdtemp(join(tmpdir(), 'petdiary-p51-'));
  const log = join(dir, 'calls.log');
  const verifyJson = verify ?? {
    ok: true,
    code: 0,
    issues: [],
    audit_count: 2,
    fingerprint_count: 2,
    new_count: 0,
    summary: '正常 2 条审计 / 2 条指纹',
  };
  const stateJson = state ?? {
    library: { name: '临时库', mode: 'single' },
    counts: { total: 2, shelf_public: 2, private: 0 },
    entries: [
      { id: 'demo.md#1', date: '2026-10-19', time: '21:10', title: '第一条' },
      { id: 'demo.md#2', date: '2026-10-19', time: '21:11', title: '第二条' },
    ],
  };
  const deleteResult = deleteJson ?? {
    ok: true,
    code: 0,
    entry: 'demo.md#2',
    mode: 'baseline',
    path: 'demo.md',
    heading: '21:11 第二条',
    audit_seq: 3,
    hash_removed: true,
  };
  const script = `
const fs = require('node:fs');
const command = process.argv[2];
fs.appendFileSync(${JSON.stringify(log)}, command + '\\n');
const VERIFY = ${JSON.stringify(verifyJson)};
const DELETE = ${JSON.stringify(deleteResult)};
if (command === 'state') {
  process.stdout.write(JSON.stringify({ ok: true, state: ${JSON.stringify(stateJson)} }) + '\\n');
} else if (command === 'verify') {
  process.stdout.write(JSON.stringify(VERIFY) + '\\n');
  process.exitCode = VERIFY.ok ? 0 : 1;
} else if (command === 'delete') {
  process.stdout.write(JSON.stringify(DELETE) + '\\n');
  process.exitCode = DELETE.ok ? 0 : 1;
} else {
  process.stdout.write(JSON.stringify({ ok: true }) + '\\n');
}
`;
  await writeFile(join(dir, 'admin.py'), script, 'utf8');
  return { dir, log };
}

test('summarizeVerify parses mismatch ids and total from a failed verify', () => {
  const summary = integrity.summarizeVerify({
    ok: false,
    code: 1,
    data: {
      ok: false,
      code: 1,
      issues: [
        '⚠ 2026-10-19-demo.md#1 被外部修改（哈希不匹配）',
        '⚠ 2026-10-19-demo.md#2 条目消失',
      ],
      audit_count: 9,
      fingerprint_count: 5,
      summary: '发现 2 个问题',
    },
  });
  assert.equal(summary.status, 'mismatch');
  assert.equal(summary.total, 5);
  assert.deepEqual(summary.ids, ['2026-10-19-demo.md#1', '2026-10-19-demo.md#2']);
  assert.deepEqual(summary.changed_ids, ['2026-10-19-demo.md#1']);
  assert.deepEqual(summary.missing_ids, ['2026-10-19-demo.md#2']);
});

test('summarizeVerify distinguishes pass, mismatch and unavailable', () => {
  const passed = integrity.summarizeVerify({
    ok: true,
    data: { ok: true, issues: [], fingerprint_count: 3, audit_count: 4 },
  });
  assert.equal(passed.status, 'ok');
  assert.equal(passed.total, 3);

  const failed = integrity.summarizeVerify({
    ok: false,
    code: 4,
    error: '找不到 Python 解释器',
    data: { ok: false, error: '找不到 Python 解释器' },
  });
  assert.equal(failed.status, 'error');
  assert.equal(failed.error, '找不到 Python 解释器');
});

test('status block copy matches the requested wording', () => {
  assert.equal(zh.integrityPassed(3), '完整性校验通过（3 条）');
  assert.equal(
    zh.integrityNotice,
    '以下条目在库外被修改过，与审计指纹不符。日记是"写完不改"的，这通常意味着直接编辑过 md 文件。可点『查看』跳到对应条目，或忽略。',
  );
  assert.equal(
    zh.integrityDeletedNotice,
    '以下条目已被删除（库外直接删的），指纹还留在基线里。可点『确认删除』清掉残留指纹，审计链会记录这次确认',
  );
  assert.equal(zh.integrityAckDelete, '确认删除');
  assert.equal(zh.integrityUnavailable('Python 不在'), '无法校验（Python 不在）');

  const okSummary = { status: 'ok', total: 3, ids: [], changed_ids: [], missing_ids: [], issues: [], checked_at: 1 };
  const badSummary = {
    status: 'mismatch',
    total: 3,
    ids: ['demo.md#1'],
    changed_ids: ['demo.md#1'],
    missing_ids: [],
    issues: ['⚠ demo.md#1 被外部修改（哈希不匹配）'],
    checked_at: 1,
  };
  const errorSummary = {
    status: 'error',
    total: 0,
    ids: [],
    changed_ids: [],
    missing_ids: [],
    issues: [],
    error: 'Python 不在',
    checked_at: 1,
  };
  assert.equal(integrity.integrityHeadline(okSummary, zh), '完整性校验通过（3 条）');
  assert.equal(integrity.integrityHeadline(badSummary, zh), zh.integrityNotice);
  assert.equal(integrity.integrityHeadline(errorSummary, zh), '无法校验（Python 不在）');
});

test('auto alert only fires on a clean -> mismatch regression', () => {
  assert.equal(integrity.shouldAlertIntegrity(null, 'mismatch'), false);
  assert.equal(integrity.shouldAlertIntegrity('mismatch', 'ok'), false);
  assert.equal(integrity.shouldAlertIntegrity('ok', 'ok'), false);
  assert.equal(integrity.shouldAlertIntegrity('mismatch', 'mismatch'), false);
  assert.equal(integrity.shouldAlertIntegrity('ok', 'mismatch'), true);
});

test('panel state queries verify once within the 60s cache window', async () => {
  const admin = await fakeAdmin();
  try {
    const world = new worldMod.PetDiaryWorld({
      cfg: cfg(admin.dir),
      packageDir: admin.dir,
    });
    const first = await world.invoke('diary', 'state');
    assert.equal(first.integrity.status, 'ok');
    assert.equal(first.integrity.total, 2);

    const second = await world.invoke('diary', 'state');
    assert.equal(second.integrity.status, 'ok');

    const calls = (await readFile(admin.log, 'utf8')).trim().split(/\r?\n/);
    assert.equal(calls.filter((call) => call === 'verify').length, 1);
  } finally {
    await rm(admin.dir, { recursive: true, force: true });
  }
});

test('panel state surfaces mismatch ids and status copy', async () => {
  const admin = await fakeAdmin({
    verify: {
      ok: false,
      code: 1,
      issues: ['⚠ demo.md#1 被外部修改（哈希不匹配）'],
      audit_count: 7,
      fingerprint_count: 3,
      summary: '发现 1 个问题',
    },
  });
  try {
    const world = new worldMod.PetDiaryWorld({
      cfg: cfg(admin.dir),
      packageDir: admin.dir,
    });
    const state = await world.invoke('diary', 'state');
    assert.equal(state.integrity.status, 'mismatch');
    assert.deepEqual(state.integrity.ids, ['demo.md#1']);
    assert.equal(state.integrity.total, 3);
    assert.equal(integrity.integrityHeadline(state.integrity, zh), zh.integrityNotice);
  } finally {
    await rm(admin.dir, { recursive: true, force: true });
  }
});

test('integrity-ack-delete calls admin delete and returns an audit receipt', async () => {
  const admin = await fakeAdmin({
    verify: {
      ok: false,
      code: 1,
      issues: ['⚠ demo.md#2 条目消失'],
      audit_count: 7,
      fingerprint_count: 3,
      summary: '发现 1 个问题',
    },
    deleteJson: {
      ok: true,
      code: 0,
      entry: 'demo.md#2',
      mode: 'baseline',
      path: 'demo.md',
      heading: '21:11 第二条',
      audit_seq: 8,
      hash_removed: true,
    },
  });
  try {
    const world = new worldMod.PetDiaryWorld({
      cfg: cfg(admin.dir),
      packageDir: admin.dir,
    });
    const result = await world.invoke('diary', 'integrity-ack-delete', ['demo.md#2']);
    assert.equal(result.ok, true);
    assert.match(result.text, /demo\.md#2/);
    assert.match(result.text, /seq=8/);
    assert.match(result.text, /action=delete/);
    const calls = (await readFile(admin.log, 'utf8')).trim().split(/\r?\n/);
    assert.ok(calls.includes('delete'));

    const tool = world.tools().find((item) => item.name === 'diary_delete');
    assert.ok(tool, '缺少 diary_delete 工具');
    const outcome = await tool.handler({ entry_id: 'demo.md#2' });
    assert.equal(outcome.failed, undefined);
    assert.match(outcome.text, /已确认删除/);
  } finally {
    await rm(admin.dir, { recursive: true, force: true });
  }
});

test('integrity-ack-delete rejects an empty entry id without calling admin', async () => {
  const admin = await fakeAdmin();
  try {
    const world = new worldMod.PetDiaryWorld({
      cfg: cfg(admin.dir),
      packageDir: admin.dir,
    });
    const result = await world.invoke('diary', 'integrity-ack-delete', ['']);
    assert.equal(result.ok, false);
    const calls = (await readFile(admin.log, 'utf8').catch(() => '')).trim().split(/\r?\n/);
    assert.ok(!calls.includes('delete'));
  } finally {
    await rm(admin.dir, { recursive: true, force: true });
  }
});

test('panel state reports unavailable instead of pretending to pass', async () => {
  const admin = await fakeAdmin();
  try {
    const world = new worldMod.PetDiaryWorld({
      cfg: cfg(admin.dir, 'definitely-no-such-python-p51'),
      packageDir: admin.dir,
    });
    const state = await world.invoke('diary', 'state');
    assert.equal(state.ok, false);
    assert.equal(state.integrity.status, 'error');
    assert.match(state.integrity.error, /找不到 Python 解释器/);
    assert.equal(
      integrity.integrityHeadline(state.integrity, zh),
      '无法校验（找不到 Python 解释器）',
    );
  } finally {
    await rm(admin.dir, { recursive: true, force: true });
  }
});

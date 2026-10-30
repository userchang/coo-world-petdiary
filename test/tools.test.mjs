import assert from 'node:assert/strict';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { loadTs } from './load-ts.mjs';

const tools = await loadTs(fileURLToPath(new URL('../src/tools.ts', import.meta.url)), 'tools');

test('append accepts a normal entry and defaults to the public book', () => {
  const result = tools.validateAppendArgs({
    time: '21:10',
    title: '被一颗阳光打败',
    body: '正文',
  });
  assert.equal(result.ok, true);
  assert.equal(result.value.book, 'daily');
  assert.equal(result.value.private, false);
});

test('append rejects bad time / kind / too-long book', () => {
  assert.equal(tools.validateAppendArgs({ book: 'daily', time: '25:00', title: 'x', body: 'y' }).ok, false);
  assert.equal(tools.validateAppendArgs({ book: 'daily', time: '21:10', title: 'x', body: 'y', kind: '其它' }).ok, false);
  assert.equal(tools.validateAppendArgs({ book: 'x'.repeat(41), time: '21:10', title: 'x', body: 'y' }).ok, false);
});

test('append rejects body with a level-2 heading', () => {
  const result = tools.validateAppendArgs({
    book: 'daily',
    time: '21:10',
    title: 'x',
    body: '第一段\n## 这不是新条目',
  });
  assert.equal(result.ok, false);
  assert.match(result.error, /二级/);
});

test('append requires private to be boolean when present', () => {
  assert.equal(tools.validateAppendArgs({
    book: 'daily', time: '21:10', title: 'x', body: 'y', private: 'yes',
  }).ok, false);
});

test('append maps book=public to the public book and book=private to the private shelf', () => {
  const publicBook = tools.validateAppendArgs({
    book: 'public', time: '21:10', title: 'x', body: 'y',
  });
  assert.equal(publicBook.ok, true);
  assert.equal(publicBook.value.book, 'daily');
  assert.equal(publicBook.value.private, false);

  const privateBook = tools.validateAppendArgs({
    book: 'private', time: '21:10', title: 'x', body: 'y',
  });
  assert.equal(privateBook.ok, true);
  assert.equal(privateBook.value.private, true);
});

test('read validates limit and scope', () => {
  const okay = tools.validateReadArgs({ limit: 5, scope: 'all' });
  assert.equal(okay.ok, true);
  assert.equal(okay.value.limit, 5);
  assert.equal(okay.value.scope, 'all');
  assert.equal(tools.validateReadArgs({ limit: 0 }).ok, false);
  assert.equal(tools.validateReadArgs({ limit: 51 }).ok, false);
  assert.equal(tools.validateReadArgs({ scope: 'private' }).ok, false);
});

test('delete validates a non-empty entry id', () => {
  const okay = tools.validateDeleteArgs({ entry_id: ' 2026-10-22-daily#2 ' });
  assert.equal(okay.ok, true);
  assert.equal(okay.value.entry_id, '2026-10-22-daily#2');
  assert.equal(tools.validateDeleteArgs({ entry_id: '' }).ok, false);
  assert.equal(tools.validateDeleteArgs({ entry_id: 42 }).ok, false);
  assert.equal(tools.validateDeleteArgs({}).ok, false);
});

test('tool descriptions embed the diary rules and stay short', () => {
  const descriptions = new Map(tools.PET_DIARY_TOOL_DECLS.map((tool) => [tool.name, tool.description]));
  assert.equal(descriptions.size, 4);
  const append = descriptions.get('diary_append');
  for (const keyword of ['append_file', 'public', 'private', '分享', '自留', '收尾']) {
    assert.match(append, new RegExp(keyword), `diary_append 缺少「${keyword}」`);
  }
  for (const banned of ['暂缓', '查重', 'visibility']) {
    assert.ok(!append.includes(banned), `diary_append 不应包含「${banned}」`);
  }
  assert.match(descriptions.get('diary_read'), /public/);
  assert.match(descriptions.get('diary_read'), /private/);
  assert.match(descriptions.get('diary_delete'), /delete|审计/);
  assert.equal(descriptions.has('diary_flip'), false);
  const total = [...descriptions.values()].reduce((sum, value) => sum + value.length, 0);
  assert.ok(total <= 700, `工具 description 合计 ${total} 字，超过 700 字预算`);
});

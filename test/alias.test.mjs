// 习惯称呼：标题里的称呼既决定说话人，也要能把条目归到「交际」。
// 称呼不写死在代码里，由插件按 config 传 PETDIARY_PARTNER_ALIAS；没有时退回「主人」。
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const repoRoot = fileURLToPath(new URL('..', import.meta.url));
const runtimePython = join(repoRoot, 'runtime', 'python', 'python.exe');
const diaryDir = join(repoRoot, 'runtime', 'diary');
const hasRuntime = existsSync(runtimePython);

/** 在内置 Python 里跑一段断言脚本，退出码 0 表示通过。 */
function runPy(code, env) {
  return execFileSync(runtimePython, ['-c', code], {
    cwd: diaryDir,
    env: { ...process.env, ...env },
    encoding: 'utf8',
  });
}

test('习惯称呼来自环境变量', { skip: !hasRuntime && '需要内置 runtime' }, () => {
  const out = runPy(
    [
      'import sys; sys.path.insert(0, ".")',
      'import parser',
      "print(parser._resolve_alias())",
      "print(parser._detect_speaker('鲸鱼今天来看我了'))",
      "kinds = parser._apply_alias(parser._load_config('kinds.json', parser.DEFAULT_KINDS))",
      "print('鲸鱼' in kinds['交际'])",
    ].join('\n'),
    { PETDIARY_PARTNER_ALIAS: '鲸鱼' },
  );
  assert.deepEqual(out.trim().split(/\r?\n/), ['鲸鱼', '鲸鱼', 'True']);
});

test('没有配置时退回「主人」', { skip: !hasRuntime && '需要内置 runtime' }, () => {
  const env = { ...process.env };
  delete env.PETDIARY_PARTNER_ALIAS;
  const out = execFileSync(
    runtimePython,
    ['-c', 'import sys; sys.path.insert(0, ".")\nimport parser\nprint(parser._resolve_alias())'],
    { cwd: diaryDir, env, encoding: 'utf8' },
  );
  assert.equal(out.trim(), '主人');
});

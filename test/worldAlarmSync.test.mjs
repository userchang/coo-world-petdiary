import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { loadTs } from './load-ts.mjs';

const here = (name) => fileURLToPath(new URL(name, import.meta.url));
const worldModule = await loadTs(here('../src/world.ts'), 'world-alarm');
const alarmSync = await loadTs(here('../src/alarmSync.ts'), 'alarmSync-world');

const TZ = 'Asia/Shanghai';

function at(hour, minute) {
  return alarmSync.localToEpoch(TZ, 2026, 10, 22, hour, minute);
}

test('World pushes once on start, again on live config change, and dedups', async () => {
  const dir = await mkdtemp(join(tmpdir(), 'petdiary-world-alarm-'));
  try {
    await writeFile(join(dir, 'alarms.json'), JSON.stringify({
      next: 2,
      alarms: [{ id: 'a5', at: at(23, 59), note: '睡前检查：旧的', daily: true, setAt: at(20, 0) }],
    }), 'utf8');

    const cfg = {
      enabled: true,
      libraryRoot: dir,
      pythonPath: '',
      scriptsDir: '',
      bedtimeCheck: '23:10',
    };
    const pushed = [];
    const host = {
      pushDeferred: (event, opts) => pushed.push({ event, opts }),
      log: { warn: () => {} },
    };

    const world = new worldModule.PetDiaryWorld({
      cfg,
      packageDir: dir,
      botDir: dir,
      timezone: TZ,
    });
    await world.start(host);
    assert.equal(pushed.length, 1);
    assert.equal(pushed[0].event.type, 'coopanion.petdiary-alarm-sync');
    assert.match(pushed[0].event.render(), /23:10/);

    // 同一配置、文件没变：不重复推。
    await world.envPromptVars();
    assert.equal(pushed.length, 1);

    // 热配置改了：envPromptVars 是已有路径，立即检查并再推一条。
    cfg.bedtimeCheck = '23:20';
    await world.envPromptVars();
    assert.equal(pushed.length, 2);
    assert.match(pushed[1].event.render(), /23:20/);

    await world.stop();
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});

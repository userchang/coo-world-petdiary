import assert from 'node:assert/strict';
import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';
import { loadTs } from './load-ts.mjs';

const alarmSync = await loadTs(
  fileURLToPath(new URL('../src/alarmSync.ts', import.meta.url)),
  'alarmSync',
);

const TZ = 'Asia/Shanghai';

function at(hour, minute, day = 22) {
  return alarmSync.localToEpoch(TZ, 2026, 10, day, hour, minute);
}

async function withAlarms(value, fn) {
  const dir = await mkdtemp(join(tmpdir(), 'petdiary-alarm-'));
  const file = join(dir, 'alarms.json');
  try {
    if (value !== undefined) await writeFile(file, value, 'utf8');
    return await fn(file, dir);
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

function alarmFile(note, when, daily = true) {
  return JSON.stringify({
    next: 6,
    alarms: [{ id: 'a5', at: when, note, daily, setAt: when - 60_000 }],
  }, null, 2);
}

test('normalizeBedtime accepts H:MM and rejects bad values', () => {
  assert.equal(alarmSync.normalizeBedtime('9:05'), '09:05');
  assert.equal(alarmSync.normalizeBedtime('23:10'), '23:10');
  assert.equal(alarmSync.normalizeBedtime('24:00'), null);
  assert.equal(alarmSync.normalizeBedtime('23:60'), null);
  assert.equal(alarmSync.normalizeBedtime('晚上十点'), null);
});

test('mismatched alarm plans an alignment event', async () => {
  await withAlarms(alarmFile('睡前检查：原来的', at(23, 59)), async (file) => {
    const plan = alarmSync.planBedtimeAlarm({
      alarmsPath: file,
      bedtime: '23:10',
      timezone: TZ,
      now: at(22, 0),
    });
    assert.equal(plan.action, 'notify');
    assert.equal(plan.reason, 'mismatch');
    assert.equal(plan.currentClock, '23:59');
    assert.equal(plan.desiredLabel, '10-22 23:10');
    assert.match(plan.key, /mismatch:a5:23:59:23:10/);
    assert.match(plan.text, /已改为 23:10/);
    assert.match(plan.text, /alarm_set/);
    assert.match(plan.text, /睡前检查/);
  });
});

test('aligned alarm is left alone', async () => {
  await withAlarms(alarmFile('睡前检查：已经对了', at(23, 10)), async (file) => {
    const plan = alarmSync.planBedtimeAlarm({
      alarmsPath: file,
      bedtime: '23:10',
      timezone: TZ,
      now: at(22, 0),
    });
    assert.equal(plan.action, 'none');
    assert.equal(plan.reason, 'aligned');
    assert.equal(plan.currentClock, '23:10');
    assert.equal(plan.text, '');
  });
});

test('broken JSON is skipped with a log, not a throw', async () => {
  await withAlarms('{ definitely not json', async (file) => {
    const plan = alarmSync.planBedtimeAlarm({
      alarmsPath: file,
      bedtime: '23:10',
      timezone: TZ,
      now: at(22, 0),
    });
    assert.equal(plan.action, 'none');
    assert.equal(plan.reason, 'file-broken');
    assert.match(plan.log, /读不了 alarms\.json/);
  });
});

test('missing alarms.json asks Coo to set the first alarm', async () => {
  await withAlarms(undefined, async (file) => {
    const plan = alarmSync.planBedtimeAlarm({
      alarmsPath: file,
      bedtime: '23:10',
      timezone: TZ,
      now: at(22, 0),
    });
    assert.equal(plan.action, 'notify');
    assert.equal(plan.reason, 'missing');
    assert.match(plan.log, /不存在/);
    assert.match(plan.text, /还没有「睡前检查」闹钟/);
    assert.match(plan.text, /daily: true/);
  });
});

test('a valid file without a bedtime alarm asks Coo to set one', async () => {
  await withAlarms(alarmFile('喝水', at(23, 0)), async (file) => {
    const plan = alarmSync.planBedtimeAlarm({
      alarmsPath: file,
      bedtime: '23:10',
      timezone: TZ,
      now: at(22, 0),
    });
    assert.equal(plan.action, 'notify');
    assert.equal(plan.reason, 'missing');
    assert.equal(plan.key, 'missing:23:10');
    assert.match(plan.text, /还没有「睡前检查」闹钟/);
  });
});

test('cross-day bedtime moves to tomorrow when today has passed', async () => {
  await withAlarms(alarmFile('睡前检查：旧的', at(23, 59)), async (file) => {
    const plan = alarmSync.planBedtimeAlarm({
      alarmsPath: file,
      bedtime: '23:10',
      timezone: TZ,
      now: at(23, 30),
    });
    assert.equal(plan.action, 'notify');
    assert.equal(plan.reason, 'mismatch');
    assert.equal(plan.desiredLabel, '10-23 23:10');
  });
});

test('same-day bedtime stays today when it is still ahead', async () => {
  await withAlarms(alarmFile('睡前检查：旧的', at(23, 59)), async (file) => {
    const plan = alarmSync.planBedtimeAlarm({
      alarmsPath: file,
      bedtime: '23:10',
      timezone: TZ,
      now: at(22, 0),
    });
    assert.equal(plan.desiredLabel, '10-22 23:10');
  });
});

test('bad bedtime config is a no-op with a log', async () => {
  await withAlarms(alarmFile('睡前检查：旧的', at(23, 59)), async (file) => {
    const plan = alarmSync.planBedtimeAlarm({
      alarmsPath: file,
      bedtime: '25:00',
      timezone: TZ,
      now: at(22, 0),
    });
    assert.equal(plan.action, 'none');
    assert.equal(plan.reason, 'bad-config');
    assert.match(plan.log, /bedtimeCheck/);
  });
});

import type { DescribeText } from 'cortico/core/types.ts';
import type { WorldDefinition, WorldDescribe } from 'cortico/world.ts';
import { ALARM_SYNC_EVENT } from './alarmSync.ts';
import { PET_DIARY_DEFAULTS, PET_DIARY_ID, type PetDiarySection } from './config.ts';
import { PET_DIARY_TOOL_DECLS } from './tools.ts';
import { PetDiaryWorld } from './world.ts';

const SUMMARIES: Record<string, DescribeText> = {
  diary_append: { zh: '给 Coo 自己的日记追加一条，并写进审计链。', en: 'Append one diary entry and record it in the audit chain.' },
  diary_read: { zh: '只读最近条目、今天写了没和各册计数。', en: 'Read recent entries, today status and per-book counts without writing audit.' },
  diary_verify: { zh: '校验审计哈希链与条目指纹，异常点名具体条目。', en: 'Verify the audit hash chain and entry fingerprints, naming any bad entry.' },
  diary_delete: { zh: '删除一条日记，整段移除并写 delete 审计，留痕不抹链。', en: 'Delete one diary entry, removing it from the markdown and recording a delete audit.' },
};

const EVENT_DESCRIBE: WorldDescribe['events'] = [{
  type: ALARM_SYNC_EVENT,
  description: {
    zh: '睡前检查时间改了：提醒桌宠用 alarm_set 把已有闹钟对齐到新时间。',
    en: 'Bedtime changed: reminds the pet to realign its existing alarm with alarm_set.',
  },
  trigger: 'flush',
}];

/** 从同一份 ToolSpec 生成 describe.tools；与实例的 tools() 不会漂移。 */
export const DESCRIBE: WorldDescribe = {
  tools: PET_DIARY_TOOL_DECLS.map(({ name, description, parameters, tags }) => ({
    name,
    description,
    parameters,
    tags,
    summary: SUMMARIES[name],
  })),
  events: EVENT_DESCRIBE,
};

export const PET_DIARY: WorldDefinition<PetDiarySection> = {
  id: PET_DIARY_ID,
  label: '桌宠日记',
  defaults: () => structuredClone(PET_DIARY_DEFAULTS),
  create: (ctx) => new PetDiaryWorld({
    cfg: ctx.cfg,
    // ctx.packageDir 是 bot 部署目录，不是插件包安装目录；world.ts 会再探测
    // 模块自身位置（import.meta.url）找内置 runtime。dataDir 由宿主直给。
    packageDir: ctx.packageDir,
    botDir: ctx.botDir,
    dataDir: ctx.dataDir,
    timezone: ctx.timezone,
  }),
  describe: DESCRIBE,
};

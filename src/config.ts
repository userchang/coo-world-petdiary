import type { ConfigGroup } from 'cortico/core/types.ts';

export const PET_DIARY_ID = 'pet-diary';
export const PET_DIARY_CONFIG_GROUP = `world:${PET_DIARY_ID}`;

/** config.json 的 `worlds.pet-diary` 段。 */
export interface PetDiarySection {
  /** 框架要求默认 false；由 bot 声明或部署配置打开。 */
  enabled: boolean;
  /** 日记库根，必须是含 index.diary 的目录。 */
  libraryRoot: string;
  /** 留空依次试 python / python3。 */
  pythonPath: string;
  /** 留空用 libraryRoot 的同级 diary/（须含 admin.py）。 */
  scriptsDir: string;
  /** 睡前检查的兜底唤醒时刻，HH:MM；默认 23:59。 */
  bedtimeCheck: string;
}

export const PET_DIARY_DEFAULTS: PetDiarySection = {
  enabled: false,
  libraryRoot: '',
  pythonPath: '',
  scriptsDir: '',
  bedtimeCheck: '23:59',
};

const PREFIX = `worlds.${PET_DIARY_ID}`;

export function configGroups(): ConfigGroup[] {
  return [{
    id: PET_DIARY_CONFIG_GROUP,
    owner: PET_DIARY_CONFIG_GROUP,
    schema: {
      type: 'object',
      title: '桌宠日记',
      description: '默认自动使用插件内置 Python 与 diary 脚本；下面的路径都可以留空，或按需覆盖。',
      properties: {
        [`${PREFIX}.libraryRoot`]: {
          type: 'string',
          title: '日记库根',
          description: '留空自动使用插件默认库（首次使用自动初始化）；也可填含 index.diary 的目录。不能指向 partner/ 或 handoffs/。',
          'x-path': { kind: 'directory' },
          'x-hot': false,
        },
        [`${PREFIX}.pythonPath`]: {
          type: 'string',
          title: 'Python 解释器',
          description: '留空自动使用插件内置 runtime/python/python.exe；不存在时依次尝试 PATH 里的 python / python3。',
          'x-path': { kind: 'file', extensions: ['.exe'] },
          'x-hot': false,
        },
        [`${PREFIX}.scriptsDir`]: {
          type: 'string',
          title: 'Python 脚本目录',
          description: '留空自动使用插件内置 runtime/diary；没有内置时回退到库根同级的 diary/。',
          'x-path': { kind: 'directory' },
          'x-hot': false,
        },
        [`${PREFIX}.bedtimeCheck`]: {
          type: 'string',
          title: '睡前检查时间',
          description: '提醒桌宠睡前查一遍今天日记写了没的兜底时刻，24 小时制 HH:MM；默认 23:59。修改后插件会检测到并推一条事件，让桌宠用 alarm_set 把已有闹钟对齐到这个时间；不会直接改 alarms.json（运行中的 Coo 只在启动时读它）。',
          pattern: '^([01]\\d|2[0-3]):[0-5]\\d$',
          'x-hot': true,
        },
      },
    },
  }];
}

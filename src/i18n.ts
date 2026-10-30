/**
 * 中文文案。暂不做英文界面，但保留 en 表结构：缺的键回落到 zh。
 * 浏览器面板与 World 声明共用这一份，避免两处措辞漂移。
 */
export type TextTable = {
  worldLabel: string;
  panelTitle: string;
  panelDescription: string;
  envTitle: string;
  envDescription: string;
  noRoot: string;
  loading: string;
  loadFailed: string;
  today: string;
  wroteToday: (count: number) => string;
  notToday: string;
  total: string;
  publicBook: string;
  privateBook: string;
  auditCount: string;
  recent: string;
  noEntries: string;
  verify: string;
  openSite: string;
  openSiteOk: (path: string) => string;
  openSiteFailed: (message: string) => string;
  verifyNormal: (count: number) => string;
  verifyBad: (count: number) => string;
  modeSingle: string;
  modeDual: string;
  recentActions: string;
  reason: string;
  integrity: string;
  integrityPassed: (count: number) => string;
  integrityNotice: string;
  integrityDeletedNotice: string;
  integrityAckDelete: string;
  integrityAlert: string;
  integrityUnavailable: (reason: string) => string;
  integrityUnknown: string;
  integrityChecking: string;
  integrityView: string;
  integrityViewMissing: (entryId: string) => string;
  integrityFlagged: string;
};

const zh: TextTable = {
  worldLabel: '桌宠日记',
  panelTitle: '日记',
  panelDescription: '最近条目、今天写了没、公开本与私密本分类、完整性检查。',
  envTitle: '桌宠日记 · 环境提示词',
  envDescription: '告诉 Coo 怎么写日记，以及公开本与私密本的区别。',
  noRoot: '还没配置日记库根。打开本页的配置，填含 index.diary 的目录。',
  loading: '正在读日记…',
  loadFailed: '读日记失败',
  today: '今天',
  wroteToday: (count) => `今天已经写了 ${count} 条`,
  notToday: '今天还没写',
  total: '合计',
  publicBook: '公开本',
  privateBook: '私密本',
  auditCount: '审计',
  recent: '最近条目',
  noEntries: '还没有条目。',
  verify: '校验完整性',
  openSite: '打开浏览页',
  openSiteOk: (path) => `浏览页已生成并在浏览器打开：${path}`,
  openSiteFailed: (message) => `打开浏览页失败：${message}`,
  verifyNormal: (count) => `正常 ${count} 条`,
  verifyBad: (count) => `发现 ${count} 个问题`,
  modeSingle: '单本',
  modeDual: '公开 / 私密两本',
  recentActions: '最近动作',
  reason: '原因',
  integrity: '完整性',
  integrityPassed: (count) => `完整性校验通过（${count} 条）`,
  integrityNotice: '以下条目在库外被修改过，与审计指纹不符。日记是"写完不改"的，这通常意味着直接编辑过 md 文件。可点『查看』跳到对应条目，或忽略。',
  integrityDeletedNotice: '以下条目已被删除（库外直接删的），指纹还留在基线里。可点『确认删除』清掉残留指纹，审计链会记录这次确认',
  integrityAckDelete: '确认删除',
  integrityAlert: '完整性校验发现异常，请查看完整性状态块',
  integrityUnavailable: (reason) => `无法校验（${reason}）`,
  integrityUnknown: '未知原因',
  integrityChecking: '正在校验完整性…',
  integrityView: '查看',
  integrityViewMissing: (entryId) => `最近条目里没有 ${entryId}`,
  integrityFlagged: '校验异常',
};

const en: Partial<TextTable> = {};

export function text(language = 'zh'): TextTable {
  if (language === 'en') return { ...zh, ...en };
  return zh;
}

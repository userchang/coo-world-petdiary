import type { ToolSpec } from 'cortico/core/types.ts';

export const KINDS = ['日常', '心情', '想法', '计划', '健康', '游戏', '交际'] as const;
export const DEFAULT_BOOK = 'daily';

export const PET_DIARY_TOOL_DECLS: readonly ToolSpec[] = [
  {
    name: 'diary_append',
    description:
      '写日记就调这个工具，不要用 append_file 手写 md。标题、时间、正文逐字段传入，不用自己拼 ## HH:MM，工具会拼。\n'
      + 'book 按内容选：public=普通记录（做了什么），会出现在对外分享页面；private=情感内容（心情、触动、委屈、喜欢、想念），只自留、永远不会被分享。拿不准写 public。\n'
      + 'kind 可选：日常/心情/想法/计划/健康/游戏/交际，按内容挑一个，不写算对。散步、买菜、感冒这类多是在描述主人的日常，也照常用。\n'
      + '一件事收尾时顺手写一条，不等定点；长短不拘，别整段抄记忆。',
    tags: ['write'],
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        book: {
          type: 'string',
          minLength: 1,
          maxLength: 40,
          default: 'public',
          description: 'public=普通记录；private=情感内容。不写默认 public。',
        },
        time: { type: 'string', pattern: '^([01]\\d|2[0-3]):[0-5]\\d$', description: 'HH:MM，24 小时制。' },
        title: { type: 'string', minLength: 1, maxLength: 200, description: '一句话标题，不要带 ##。' },
        body: { type: 'string', minLength: 1, maxLength: 20000, description: '正文；不要写二级/三级标题。' },
        kind: { type: 'string', enum: [...KINDS], description: '可选：日常 / 心情 / 想法 / 计划 / 健康 / 游戏 / 交际。' },
      },
      required: ['time', 'title', 'body'],
    },
  },
  {
    name: 'diary_read',
    description:
      '读日记：公开本（public）和私密本（private）都能读，私密无任何限制。\n'
      + '返回最近条目、今天写了没、各册计数；只读，不写审计。\n'
      + 'scope=public 只看公开本；scope=all 连私密本一起读。',
    tags: ['read'],
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        book: { type: 'string', description: '只看某一册。' },
        limit: { type: 'integer', minimum: 1, maximum: 50, default: 5 },
        scope: { type: 'string', enum: ['public', 'all'], default: 'public' },
      },
      required: [],
    },
  },
  {
    name: 'diary_verify',
    description:
      '校验日记库的审计哈希链与条目指纹。正常时返回「正常 N 条」；异常会点名具体条目。只报不修。',
    tags: ['read', 'snapshot'],
    parameters: { type: 'object', additionalProperties: false, properties: {}, required: [] },
  },
  {
    name: 'diary_delete',
    description:
      '删除一条日记，只在用户明确要求删除时用。\n'
      + '删除是留痕操作：会整段移除 md 里的条目、清掉该条的基线指纹，并追加一条 action=delete 的审计记录；审计链本身永远不会被抹掉。\n'
      + 'entry_id 从 diary_read / diary_verify / 面板里拿；库外直接被删掉的条目也能用它清残留指纹。',
    tags: ['write'],
    parameters: {
      type: 'object',
      additionalProperties: false,
      properties: {
        entry_id: { type: 'string', minLength: 1, description: '要删除的条目 id，例如 2026-10-22-daily#2。' },
      },
      required: ['entry_id'],
    },
  },
];

export interface AppendArgs {
  book: string;
  time: string;
  title: string;
  body: string;
  kind?: string;
  private: boolean;
}

export interface ReadArgs {
  book?: string;
  limit: number;
  scope: 'public' | 'all';
}

export interface DeleteArgs {
  entry_id: string;
}

export type Validated<T> = { ok: true; value: T } | { ok: false; error: string };

const text = (value: unknown): string => (typeof value === 'string' ? value.trim() : '');

export function validateAppendArgs(args: Record<string, unknown>): Validated<AppendArgs> {
  const requestedBook = text(args.book) || 'public';
  const time = text(args.time);
  const title = text(args.title);
  const body = typeof args.body === 'string' ? args.body.replace(/\r\n?/g, '\n').trim() : '';
  const kind = args.kind === undefined || args.kind === null || args.kind === '' ? undefined : text(args.kind);
  const isPrivate = args.private === true || requestedBook.toLowerCase() === 'private';
  const book = requestedBook.toLowerCase() === 'public' ? DEFAULT_BOOK : requestedBook;

  if (requestedBook.length > 40) return { ok: false, error: 'book 最多 40 个字符' };
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(time)) return { ok: false, error: 'time 必须是 HH:MM（24 小时制）' };
  if (!title) return { ok: false, error: 'title 不能为空' };
  if (title.length > 200) return { ok: false, error: 'title 最多 200 个字符' };
  if (!body) return { ok: false, error: 'body 不能为空' };
  if (body.length > 20000) return { ok: false, error: 'body 最多 20000 个字符' };
  if (kind !== undefined && !(KINDS as readonly string[]).includes(kind)) {
    return { ok: false, error: `kind 只能是 ${KINDS.join(' / ')}` };
  }
  if (/^\s*#{2,3}\s/m.test(body)) {
    return { ok: false, error: 'body 里不能出现二级/三级标题，否则会被拆成新条目' };
  }
  if (args.private !== undefined && typeof args.private !== 'boolean') {
    return { ok: false, error: 'private 必须是布尔值' };
  }
  return { ok: true, value: { book, time, title, body, kind, private: isPrivate } };
}

export function validateReadArgs(args: Record<string, unknown>): Validated<ReadArgs> {
  const bookRaw = args.book;
  if (bookRaw !== undefined && typeof bookRaw !== 'string') return { ok: false, error: 'book 必须是字符串' };
  const book = text(bookRaw) || undefined;
  const limitRaw = args.limit === undefined || args.limit === null ? 5 : Number(args.limit);
  if (!Number.isInteger(limitRaw) || limitRaw < 1 || limitRaw > 50) {
    return { ok: false, error: 'limit 必须是 1–50 的整数' };
  }
  const scope = args.scope === undefined || args.scope === null || args.scope === '' ? 'public' : text(args.scope);
  if (scope !== 'public' && scope !== 'all') return { ok: false, error: 'scope 只能是 public 或 all' };
  return { ok: true, value: { book, limit: limitRaw, scope } };
}

export function validateDeleteArgs(args: Record<string, unknown>): Validated<DeleteArgs> {
  if (typeof args.entry_id !== 'string') return { ok: false, error: 'entry_id 必须是字符串' };
  const entry_id = args.entry_id.trim();
  if (!entry_id) return { ok: false, error: 'entry_id 不能为空' };
  return { ok: true, value: { entry_id } };
}

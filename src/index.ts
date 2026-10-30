/** 包入口：默认导出 `WorldDefinition`，加载器按 cortico.kind === 'world' 认它。 */
import { PET_DIARY } from './definition.ts';

export default PET_DIARY;
export { PET_DIARY };
export { PET_DIARY_ID, PET_DIARY_DEFAULTS } from './config.ts';
export type { PetDiarySection } from './config.ts';

import type {TerminalRecord,SourceUpdate} from './api/terminalDocument'
import type {OcrItem} from './types/ocr'
export function planTableSync(before:TerminalRecord[],after:TerminalRecord[],items:OcrItem[]) {
  const updates=new Map<string,SourceUpdate>(), skipped=new Set<string>(),shared=new Set<string>()
  for(const row of after) {
    const original=before.find(r=>r.id===row.id)
    if(!original) continue
    for(const [field,target] of [['cable','text'],['terminalNumber','terminal_number']] as const) {
      if(row[field]===original[field]) continue
      const source=items.find(i=>i.id===row.sourceResultId && i.reviewStatus!=='deleted' && i.reviewStatus!=='false_positive')
      if(!source || row.sourceResultId!==original.sourceResultId) {skipped.add(row.id);continue}
      const update=updates.get(source.id) || {result_id:source.id,base_revision:source.revision || 0,base_table_revision:source.tableRevision || 0}
      if(update[target]!==undefined && update[target]!==row[field]) throw Error('多行对同一 OCR 来源填写了不同值，请分别核对后修改')
      update[target]=row[field];updates.set(source.id,update)
      if(before.filter(r=>r.sourceResultId===source.id).length>1) shared.add(source.id)
    }
  }
  return {updates:[...updates.values()],skipped:skipped.size,shared}
}

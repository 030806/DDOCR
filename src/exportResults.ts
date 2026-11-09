import type { OcrItem, TerminalPoint } from './types/ocr'
import { exportableOcrItems } from './resultVisibility'
import { independentTerminalTableRows } from './terminalPairTable'

export type ExportMode = 'simple' | 'full'

export type SimpleExportRow = {
  编号: string
  端子排最终识别结果: string
}

export type FullExportRow = {
  编号: string
  原始识别结果: string
  纠正结果: string
  最终识别结果: string
  留言人: string
  留言结果: string
}

function formatIndex(index: number) {
  return String(index + 1).padStart(2, '0')
}

export function createSimpleExportRows(items: OcrItem[]): SimpleExportRow[] {
  return exportableOcrItems(items).map((item, index) => ({
    编号: formatIndex(index),
    端子排最终识别结果: item.corrected ?? item.text,
  }))
}

export function createFullExportRows(items: OcrItem[]): FullExportRow[] {
  return exportableOcrItems(items).flatMap((item, index) => {
    const baseRow = {
      编号: formatIndex(index),
      原始识别结果: item.text,
      纠正结果: item.corrected || '',
      最终识别结果: item.corrected ?? item.text,
    }
    const comments = item.comments.length ? item.comments : [{ author: '', content: '' }]

    return comments.map((comment) => ({
      ...baseRow,
      留言人: comment.author,
      留言结果: comment.content,
    }))
  })
}

function formatDate(date: Date) {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}${month}${day}`
}

export async function exportOcrResults(items: OcrItem[], mode: ExportMode, pageNo: number, terminalPoints?: TerminalPoint[] | null) {
  const XLSX = await import('xlsx')
  const rows = mode === 'simple' ? createSimpleExportRows(items) : createFullExportRows(items)
  const worksheet = XLSX.utils.json_to_sheet(rows)
  worksheet['!cols'] = mode === 'simple'
    ? [{ wch: 10 }, { wch: 48 }]
    : [{ wch: 10 }, { wch: 32 }, { wch: 32 }, { wch: 32 }, { wch: 14 }, { wch: 40 }]

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, mode === 'simple' ? '精简结果' : '完整结果')
  if (terminalPoints) {
    const pairRows = independentTerminalTableRows(terminalPoints, items).map(row => ({
      端子号: row.terminalNumber,
      线号: row.item?.corrected ?? row.item?.text ?? '',
      匹配状态: '仅并排，未确认',
    }))
    const pairSheet = XLSX.utils.json_to_sheet(pairRows, { header: ['端子号', '线号', '匹配状态'] })
    pairSheet['!cols'] = [{ wch: 12 }, { wch: 40 }, { wch: 20 }]
    XLSX.utils.book_append_sheet(workbook, pairSheet, '端子对照表')
  }
  const modeLabel = mode === 'simple' ? '精简' : '完整'
  XLSX.writeFile(workbook, `OCR结果_第${pageNo}页_${modeLabel}_${formatDate(new Date())}.xlsx`)
}


export function createBusinessExportRows(items: OcrItem[]) {
  return items.map(item => ({ 端子号: item.terminalNumber ?? '', 线号: item.corrected ?? item.text,
    匹配状态: item.businessAssociationStatus === 'manual' ? '人工填写，无检测框' : item.terminalPointId ? '已匹配' : '仅并排，未确认',
    备注: item.tableNote ?? '', 人工确认: item.manualConfirmed ? '是' : '否' }))
}

export async function exportTerminalBusiness(items: OcrItem[], mode: ExportMode, pageNo: number) {
  const XLSX = await import('xlsx')
  const rows = createBusinessExportRows(items).map(row => mode === 'simple' ? { 端子号: row.端子号, 线号: row.线号, 匹配状态: row.匹配状态 } : row)
  const workbook = XLSX.utils.book_new()
  const sheet = XLSX.utils.json_to_sheet(rows)
  sheet['!cols'] = [{ wch: 16 }, { wch: 40 }, { wch: 20 }, { wch: 40 }, { wch: 12 }]
  XLSX.utils.book_append_sheet(workbook, sheet, '端子对照表')
  XLSX.writeFile(workbook, `端子最终结果_第${pageNo}页_${formatDate(new Date())}.xlsx`)
}

import type { OcrItem } from './types/ocr'

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
  return items.map((item, index) => ({
    编号: formatIndex(index),
    端子排最终识别结果: item.corrected || item.text,
  }))
}

export function createFullExportRows(items: OcrItem[]): FullExportRow[] {
  return items.flatMap((item, index) => {
    const baseRow = {
      编号: formatIndex(index),
      原始识别结果: item.text,
      纠正结果: item.corrected || '',
      最终识别结果: item.corrected || item.text,
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

export async function exportOcrResults(items: OcrItem[], mode: ExportMode, pageNo: number) {
  const XLSX = await import('xlsx')
  const rows = mode === 'simple' ? createSimpleExportRows(items) : createFullExportRows(items)
  const worksheet = XLSX.utils.json_to_sheet(rows)
  worksheet['!cols'] = mode === 'simple'
    ? [{ wch: 10 }, { wch: 48 }]
    : [{ wch: 10 }, { wch: 32 }, { wch: 32 }, { wch: 32 }, { wch: 14 }, { wch: 40 }]

  const workbook = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(workbook, worksheet, mode === 'simple' ? '精简结果' : '完整结果')
  const modeLabel = mode === 'simple' ? '精简' : '完整'
  XLSX.writeFile(workbook, `OCR结果_第${pageNo}页_${modeLabel}_${formatDate(new Date())}.xlsx`)
}

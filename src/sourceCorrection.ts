import type { OcrItem } from './types/ocr'
export function sourceCorrectionUnavailable(item?: OcrItem): string {
  if (!item || item.id.startsWith('terminal:') || item.terminalPointId) return '此行暂无关联识别框'
  if (item.reviewStatus === 'deleted' || item.reviewStatus === 'false_positive') return '来源已删除或标记误检，请先核对并恢复来源'
  return ''
}
export function sourcePreviewStyle(item: OcrItem, width: number, height: number) {
  const [x1, y1, x2, y2] = item.bbox
  const scale = Math.min(3, 440 / Math.max(1, x2 - x1), 140 / Math.max(1, y2 - y1))
  return { width: `${Math.max(1, x2 - x1) * scale}px`, height: `${Math.max(1, y2 - y1) * scale}px`,
    backgroundSize: `${width * scale}px ${height * scale}px`, backgroundPosition: `${-x1 * scale}px ${-y1 * scale}px` }
}

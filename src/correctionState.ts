import type { OcrItem } from './types/ocr'

export function applyCorrectionToItems(
  items: OcrItem[], resultId: string, correctedText: string, revision: number,
): boolean {
  const item = items.find(value => value.id === resultId)
  if (!item) return false
  item.corrected = correctedText
  item.revision = revision
  return true
}

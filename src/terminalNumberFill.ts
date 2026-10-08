import type { OcrItem } from './types/ocr'

export function terminalNumberFillValues(items: OcrItem[], selectedIds: string[]): Map<string, string> {
  const selected = new Set(selectedIds)
  return new Map(items.flatMap((item, index) =>
    selected.has(item.id) && !item.terminalNumber?.trim()
      ? [[item.id, String(index + 1)] as const]
      : [],
  ))
}

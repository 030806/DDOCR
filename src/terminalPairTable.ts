import type { OcrItem, TerminalPoint } from './types/ocr'
import { sortOcrItemsByCoordinates } from './ocrResultOrder'
import { exportableOcrItems } from './resultVisibility'

export type TerminalTableRow = {
  selectionId: string
  index: number
  terminalNumber: string
  item?: OcrItem
  hasTerminal: boolean
  hasOcrResult: boolean
  requiresTerminalReview: boolean
}

export function orderedTerminalPoints(points: TerminalPoint[]): TerminalPoint[] {
  return [...points].sort((a, b) => a.y - b.y || a.x - b.x || a.id.localeCompare(b.id))
}

export function terminalTableRows(points: TerminalPoint[], items: OcrItem[]): TerminalTableRow[] {
  const orderedPoints = orderedTerminalPoints(points)
  const orderedLines = sortOcrItemsByCoordinates(exportableOcrItems(items))
  const count = Math.max(points.length, orderedLines.length)
  return Array.from({ length: count }, (_, index) => ({
    selectionId: orderedLines[index]?.id || `terminal:${orderedPoints[index]!.id}`,
    index: index + 1,
    terminalNumber: orderedLines[index]?.terminalNumber || (index < points.length ? String(index + 1) : ''),
    item: orderedLines[index],
    hasTerminal: index < points.length,
    hasOcrResult: !!orderedLines[index],
    requiresTerminalReview: index >= points.length && !!orderedLines[index],
  }))
}

import type { OcrItem, TerminalPoint } from './types/ocr'
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

export function gridTerminalNumber(row: Pick<TerminalTableRow, 'hasTerminal' | 'terminalNumber'>, saved: string): string {
  return row.hasTerminal ? saved || row.terminalNumber : ''
}

function lineCenter(item: OcrItem): { x: number; y: number } {
  return { x: (item.bbox[0] + item.bbox[2]) / 2, y: (item.bbox[1] + item.bbox[3]) / 2 }
}

function logicalLineY(item: OcrItem, terminalX: number): number {
  const center = lineCenter(item)
  const polygon = item.polygon
  if (!polygon) return center.y
  const dx = ((polygon[1][0] - polygon[0][0]) + (polygon[2][0] - polygon[3][0])) / 2
  const dy = ((polygon[1][1] - polygon[0][1]) + (polygon[2][1] - polygon[3][1])) / 2
  if (Math.abs(dx) < 8 || Math.abs(dy / dx) > 0.35) return center.y
  return center.y + (dy / dx) * (terminalX - center.x)
}

function lineRank(item: OcrItem, distance: number): [number, number, string] {
  return [distance, lineCenter(item).y, item.id]
}

function isBetter(candidate: [number, number, string], current: [number, number, string]): boolean {
  return candidate[0] < current[0] ||
    (candidate[0] === current[0] && (candidate[1] < current[1] ||
      (candidate[1] === current[1] && candidate[2].localeCompare(current[2]) < 0)))
}

export function terminalTableRows(points: TerminalPoint[], items: OcrItem[]): TerminalTableRow[] {
  const orderedPoints = orderedTerminalPoints(points)
  const lines = exportableOcrItems(items)
  const winners = new Map<string, { item: OcrItem; rank: [number, number, string] }>()
  const unmatched: OcrItem[] = []

  for (const item of lines) {
    if (!orderedPoints.length) {
      unmatched.push(item)
      continue
    }
    const nearest = orderedPoints.map(point => ({
      point,
      distance: Math.abs(logicalLineY(item, point.x) - point.y),
    })).sort((a, b) => a.distance - b.distance || a.point.y - b.point.y ||
      a.point.x - b.point.x || a.point.id.localeCompare(b.point.id))[0]
    const rank = lineRank(item, nearest.distance)
    const incumbent = winners.get(nearest.point.id)
    if (incumbent && !isBetter(rank, incumbent.rank)) {
      unmatched.push(item)
    } else {
      if (incumbent) unmatched.push(incumbent.item)
      winners.set(nearest.point.id, { item, rank })
    }
  }

  const rows = [
    ...orderedPoints.map((point, index) => {
      const item = winners.get(point.id)?.item
      return { y: point.y, x: point.x, terminal: true, selectionId: item?.id || `terminal:${point.id}`,
        terminalNumber: item?.terminalNumber?.trim() || String(index + 1), item }
    }),
    ...unmatched.map(item => ({ y: lineCenter(item).y, x: lineCenter(item).x, terminal: false,
      selectionId: item.id, terminalNumber: '', item })),
  ].sort((a, b) => a.y - b.y || Number(b.terminal) - Number(a.terminal) || a.x - b.x ||
    a.selectionId.localeCompare(b.selectionId))

  return rows.map((row, index) => ({
    selectionId: row.selectionId, index: index + 1,
    terminalNumber: row.terminalNumber, item: row.item,
    hasTerminal: row.terminal,
    hasOcrResult: !!row.item,
    requiresTerminalReview: !row.terminal && !!row.item,
  }))
}

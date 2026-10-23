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

function terminalPitch(points: TerminalPoint[]): number {
  const gaps = points.slice(1).map((point, index) => point.y - points[index]!.y)
    .filter(gap => Number.isFinite(gap) && gap > 0).sort((a, b) => a - b)
  if (!gaps.length) return 0
  const middle = Math.floor(gaps.length / 2)
  return gaps.length % 2 ? gaps[middle]! : (gaps[middle - 1]! + gaps[middle]!) / 2
}

function logicalLineY(item: OcrItem, terminalX: number, pitch: number): number {
  const center = lineCenter(item)
  const polygon = item.polygon
  if (!polygon || polygon.length !== 4 || pitch <= 0) return center.y
  const dx = ((polygon[1][0] - polygon[0][0]) + (polygon[2][0] - polygon[3][0])) / 2
  const dy = ((polygon[1][1] - polygon[0][1]) + (polygon[2][1] - polygon[3][1])) / 2
  const slope = dy / dx
  if (!Number.isFinite(slope) || Math.abs(dx) < 8 || Math.abs(slope) > 0.35) return center.y
  const correction = slope * (terminalX - center.x)
  const boxHeight = Math.max(0, item.bbox[3] - item.bbox[1])
  const limit = Math.min(pitch * 0.35, Math.max(12, boxHeight * 1.5))
  return Number.isFinite(correction) && Math.abs(correction) <= limit ? center.y + correction : center.y
}

type NearestPoint = { index: number; distance: number }

function nearestPoint(item: OcrItem, points: TerminalPoint[], pitch: number): { projected: NearestPoint; center: NearestPoint } {
  const centerY = lineCenter(item).y
  const closest = (projected: boolean): NearestPoint => points.map((point, index) => ({
    index, distance: Math.abs((projected ? logicalLineY(item, point.x, pitch) : centerY) - point.y),
  })).sort((a, b) => a.distance - b.distance || a.index - b.index)[0]!
  const center = closest(false)
  const projected = closest(true)
  if (projected.index === center.index) return { projected, center }
  const gap = Math.abs(points[projected.index]!.y - points[center.index]!.y)
  const centerCostGap = Math.abs(centerY - points[projected.index]!.y) - center.distance
  // A slope may resolve an ambiguous row boundary, but cannot move a line
  // from a clearly nearer terminal to another row.
  if (Math.abs(projected.index - center.index) !== 1 || gap === 0 || centerCostGap > gap * 0.2) {
    return { projected: center, center }
  }
  return { projected, center }
}

function assignmentsCross(proposals: Array<{ item: OcrItem; projected: NearestPoint }>): boolean {
  const ordered = [...proposals].sort((a, b) => lineCenter(a.item).y - lineCenter(b.item).y ||
    lineCenter(a.item).x - lineCenter(b.item).x || a.item.id.localeCompare(b.item.id))
  let highestPointIndex = -1
  for (const proposal of ordered) {
    if (proposal.projected.index < highestPointIndex) return true
    highestPointIndex = Math.max(highestPointIndex, proposal.projected.index)
  }
  return false
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
  const available = exportableOcrItems(items)
  const bound = new Map(available.filter(item => item.terminalPointId).map(item => [item.terminalPointId!, item]))
  const lines = available.filter(item => !item.terminalPointId || !orderedPoints.some(p => p.id === item.terminalPointId))
  const winners = new Map<string, { item: OcrItem; rank: [number, number, string] }>()
  const unmatched: OcrItem[] = []

  const pitch = terminalPitch(orderedPoints)
  const proposals = orderedPoints.length ? lines.map(item => ({ item, ...nearestPoint(item, orderedPoints, pitch) })) : []
  // If independent polygon projections reverse the order of adjacent lines,
  // re-evaluate this page from box centers. This retains the nearest-point
  // rule and avoids reassigning a losing line to its second-nearest point.
  const useCenter = assignmentsCross(proposals)

  if (!orderedPoints.length) unmatched.push(...lines)
  for (const proposal of proposals) {
    const { item } = proposal
    const nearest = useCenter ? proposal.center : proposal.projected
    const point = orderedPoints[nearest.index]!
    const rank = lineRank(item, nearest.distance)
    const incumbent = winners.get(point.id)
    if (incumbent && !isBetter(rank, incumbent.rank)) {
      unmatched.push(item)
    } else {
      if (incumbent) unmatched.push(incumbent.item)
      winners.set(point.id, { item, rank })
    }
  }

  for (const [pointId, winner] of winners) {
    if (bound.has(pointId)) unmatched.push(winner.item)
  }
  const rows = [
    ...orderedPoints.map((point, index) => {
      const item = bound.get(point.id) || winners.get(point.id)?.item
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

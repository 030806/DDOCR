import { canvasPointToSource, type ImageTransform } from './bboxEditing'
import type { TerminalPoint } from './types/ocr'

export function terminalPointChanges(before: TerminalPoint[], after: TerminalPoint[]) {
  const previous = new Set(before.map(point => point.id)), next = new Set(after.map(point => point.id))
  const added = after.filter(point => !previous.has(point.id)).length
  const deleted = before.filter(point => !next.has(point.id)).length
  return { before: before.length, after: after.length, added, deleted, requiresConfirmation: added > 0 || deleted > 0 }
}

export function terminalPointConfirmationText(before: TerminalPoint[], after: TerminalPoint[]) {
  const change = terminalPointChanges(before, after)
  return `本次新增 ${change.added} 个、删除 ${change.deleted} 个端子点。端子数量将从 ${change.before} 变为 ${change.after}，端子对照表将按坐标重新排列，请核对线号对应关系。`
}

export async function saveWithTerminalPointConfirmation(before: TerminalPoint[], after: TerminalPoint[], confirm: (text: string) => Promise<boolean>, persist: () => Promise<void>) {
  if (terminalPointChanges(before, after).requiresConfirmation && !await confirm(terminalPointConfirmationText(before, after))) return false
  await persist()
  return true
}

/** Convert a stage pointer to the object payload used by terminal point events. */
export function terminalPointFromPointer(
  pointer: { x: number; y: number }, zoom: number, transform: ImageTransform,
): { x: number; y: number } | undefined {
  if (!Number.isFinite(zoom) || zoom <= 0) return
  const canvas = { x: pointer.x / zoom, y: pointer.y / zoom }
  if (!Number.isFinite(canvas.x) || !Number.isFinite(canvas.y)
    || canvas.x < transform.x || canvas.x > transform.x + transform.sourceWidth * transform.scale
    || canvas.y < transform.y || canvas.y > transform.y + transform.sourceHeight * transform.scale) return
  const [x, y] = canvasPointToSource(canvas, transform)
  return { x, y }
}

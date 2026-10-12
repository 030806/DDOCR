import { canvasPointToSource, type ImageTransform } from './bboxEditing'

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

export type DragOffset = { x: number; y: number }
export type DragBounds = { left: number; top: number; right: number; bottom: number }

export function boundedModalOffset(
  start: DragOffset,
  bounds: DragBounds,
  viewport: { width: number; height: number },
  movement: DragOffset,
  margin = 16,
): DragOffset {
  const clamp = (value: number, lower: number, upper: number) =>
    lower > upper ? value : Math.min(upper, Math.max(lower, value))
  return {
    x: start.x + clamp(movement.x, margin - bounds.left, viewport.width - margin - bounds.right),
    y: start.y + clamp(movement.y, margin - bounds.top, viewport.height - margin - bounds.bottom),
  }
}

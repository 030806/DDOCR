import type { OcrItem, OcrPolygon } from './types/ocr'

export type Bbox = OcrItem['bbox']
export type CanvasRect = { x: number; y: number; width: number; height: number }
export type ImageTransform = { x: number; y: number; scale: number; sourceWidth: number; sourceHeight: number }
export type CanvasPoint = { x: number; y: number }

export const RESULT_BOX_COLOR = '#b6bfbc'
export const SELECTED_BOX_COLOR = '#ff4d4f'

export function resultBoxColor(selected: boolean): string {
  return selected ? SELECTED_BOX_COLOR : RESULT_BOX_COLOR
}

export type EditableOcrItem = OcrItem & {
  editSource?: 'ocr' | 'manual'
  editOperation?: 'unchanged' | 'updated' | 'created' | 'deleted'
  geometryRevision?: number
  originalBbox?: Bbox
  originalPolygon?: OcrPolygon
}

const rounded = (value: number) => Math.round(value * 100) / 100
const clamp = (value: number, maximum: number) => Math.min(maximum, Math.max(0, value))

export function normalizeBbox(bbox: Bbox, sourceWidth: number, sourceHeight: number, minimumSize = 4): Bbox {
  let x1 = clamp(Math.min(bbox[0], bbox[2]), sourceWidth)
  let y1 = clamp(Math.min(bbox[1], bbox[3]), sourceHeight)
  let x2 = clamp(Math.max(bbox[0], bbox[2]), sourceWidth)
  let y2 = clamp(Math.max(bbox[1], bbox[3]), sourceHeight)
  if (x2 - x1 < minimumSize) x2 = Math.min(sourceWidth, x1 + minimumSize)
  if (y2 - y1 < minimumSize) y2 = Math.min(sourceHeight, y1 + minimumSize)
  if (x2 - x1 < minimumSize) x1 = Math.max(0, x2 - minimumSize)
  if (y2 - y1 < minimumSize) y1 = Math.max(0, y2 - minimumSize)
  return [x1, y1, x2, y2].map(rounded) as Bbox
}

export function bboxToPolygon(bbox: Bbox): OcrPolygon {
  return [[bbox[0], bbox[1]], [bbox[2], bbox[1]], [bbox[2], bbox[3]], [bbox[0], bbox[3]]]
}

export function normalizePolygon(polygon: OcrPolygon, sourceWidth: number, sourceHeight: number): OcrPolygon {
  return polygon.map(([x, y]) => [rounded(clamp(x, sourceWidth)), rounded(clamp(y, sourceHeight))]) as OcrPolygon
}

export function polygonToBbox(polygon: OcrPolygon, sourceWidth: number, sourceHeight: number): Bbox {
  const normalized = normalizePolygon(polygon, sourceWidth, sourceHeight)
  const xs = normalized.map(point => point[0])
  const ys = normalized.map(point => point[1])
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)].map(rounded) as Bbox
}

export function sourcePointToCanvas(point: [number, number], transform: ImageTransform): CanvasPoint {
  return { x: transform.x + point[0] * transform.scale, y: transform.y + point[1] * transform.scale }
}

export function canvasPointToSource(point: CanvasPoint, transform: ImageTransform): [number, number] {
  return [
    rounded(clamp((point.x - transform.x) / transform.scale, transform.sourceWidth)),
    rounded(clamp((point.y - transform.y) / transform.scale, transform.sourceHeight)),
  ]
}

export function polygonToCanvasPoints(polygon: OcrPolygon, transform: ImageTransform): number[] {
  return polygon.flatMap(point => {
    const mapped = sourcePointToCanvas(point, transform)
    return [mapped.x, mapped.y]
  })
}

export function translatePolygonWithinBounds(
  polygon: OcrPolygon, requestedX: number, requestedY: number,
  sourceWidth: number, sourceHeight: number,
): OcrPolygon {
  const xs = polygon.map(point => point[0])
  const ys = polygon.map(point => point[1])
  const dx = Math.min(sourceWidth - Math.max(...xs), Math.max(-Math.min(...xs), requestedX))
  const dy = Math.min(sourceHeight - Math.max(...ys), Math.max(-Math.min(...ys), requestedY))
  return polygon.map(([x, y]) => [rounded(x + dx), rounded(y + dy)]) as OcrPolygon
}

function orientation(a: [number, number], b: [number, number], c: [number, number]) {
  return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
}

function segmentsCross(a: [number, number], b: [number, number], c: [number, number], d: [number, number]) {
  return orientation(a, b, c) * orientation(a, b, d) < 0
    && orientation(c, d, a) * orientation(c, d, b) < 0
}

export function isValidPolygon(polygon: OcrPolygon, minimumArea = 16): boolean {
  if (polygon.some(point => point.some(value => !Number.isFinite(value)))) return false
  const xs = polygon.map(point => point[0])
  const ys = polygon.map(point => point[1])
  if (Math.max(...xs) - Math.min(...xs) < 4 || Math.max(...ys) - Math.min(...ys) < 4) return false
  if (segmentsCross(polygon[0], polygon[1], polygon[2], polygon[3])) return false
  if (segmentsCross(polygon[1], polygon[2], polygon[3], polygon[0])) return false
  const twiceArea = Math.abs(polygon.reduce((sum, point, index) => {
    const next = polygon[(index + 1) % polygon.length]
    return sum + point[0] * next[1] - next[0] * point[1]
  }, 0))
  return twiceArea >= minimumArea * 2
}

export function bboxToCanvasRect(bbox: Bbox, transform: ImageTransform): CanvasRect {
  return {
    x: transform.x + bbox[0] * transform.scale,
    y: transform.y + bbox[1] * transform.scale,
    width: (bbox[2] - bbox[0]) * transform.scale,
    height: (bbox[3] - bbox[1]) * transform.scale,
  }
}

export function canvasRectToBbox(rect: CanvasRect, transform: ImageTransform): Bbox {
  return normalizeBbox([
    (rect.x - transform.x) / transform.scale,
    (rect.y - transform.y) / transform.scale,
    (rect.x + rect.width - transform.x) / transform.scale,
    (rect.y + rect.height - transform.y) / transform.scale,
  ], transform.sourceWidth, transform.sourceHeight)
}

export function cloneEditableItems(items: EditableOcrItem[]): EditableOcrItem[] {
  return items.map(item => ({
    ...item,
    bbox: [...item.bbox] as Bbox,
    polygon: item.polygon?.map(point => [...point]) as OcrPolygon | undefined,
    originalBbox: item.originalBbox ? [...item.originalBbox] as Bbox : undefined,
    originalPolygon: item.originalPolygon?.map(point => [...point]) as OcrPolygon | undefined,
    comments: item.comments.map(comment => ({ ...comment })),
  }))
}

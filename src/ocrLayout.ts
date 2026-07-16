import type { OcrItem } from './mock'

export type ResultViewMode = 'list' | 'layout'

export const OCR_DOCUMENT_WIDTH = 700
export const OCR_DOCUMENT_HEIGHT = 760

export type RelativeLayoutBox = {
  left: number
  top: number
  width: number
  height: number
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(maximum, Math.max(minimum, value))
}

export function mapBboxToRelative(
  bbox: OcrItem['bbox'],
  documentWidth = OCR_DOCUMENT_WIDTH,
  documentHeight = OCR_DOCUMENT_HEIGHT,
): RelativeLayoutBox {
  const safeWidth = Math.max(1, documentWidth)
  const safeHeight = Math.max(1, documentHeight)
  const x1 = clamp(Math.min(bbox[0], bbox[2]), 0, safeWidth)
  const y1 = clamp(Math.min(bbox[1], bbox[3]), 0, safeHeight)
  const x2 = clamp(Math.max(bbox[0], bbox[2]), x1, safeWidth)
  const y2 = clamp(Math.max(bbox[1], bbox[3]), y1, safeHeight)

  return {
    left: (x1 / safeWidth) * 100,
    top: (y1 / safeHeight) * 100,
    width: ((x2 - x1) / safeWidth) * 100,
    height: ((y2 - y1) / safeHeight) * 100,
  }
}

export function getFinalOcrText(item: OcrItem) {
  return item.corrected || item.text
}

export function getLayoutCanvasHeight(canvasWidth: number, documentWidth = OCR_DOCUMENT_WIDTH, documentHeight = OCR_DOCUMENT_HEIGHT) {
  return Math.max(0, canvasWidth) * (documentHeight / Math.max(1, documentWidth))
}

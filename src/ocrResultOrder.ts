import type { OcrItem } from './types/ocr'

// Return a display-only copy ordered from top to bottom, then left to right.
export function sortOcrItemsByCoordinates(items: OcrItem[]): OcrItem[] {
  return items
    .map((item, index) => ({ item, index }))
    .sort((left, right) => {
      const coordinateOrder = left.item.bbox[1] - right.item.bbox[1]
        || left.item.bbox[0] - right.item.bbox[0]
        || left.item.bbox[3] - right.item.bbox[3]
        || left.item.bbox[2] - right.item.bbox[2]
      return coordinateOrder || left.index - right.index
    })
    .map(({ item }) => item)
}

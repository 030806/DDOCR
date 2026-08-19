import type { OcrItem } from './types/ocr'

export type ResultFilters = {
  search: string
  minimumConfidence: number
  lowOnly: boolean
  lowConfidenceThreshold: number
  showFalsePositive: boolean
  showDeleted: boolean
}

export function isExcludedFromExport(item: OcrItem): boolean {
  return item.reviewStatus === 'deleted' || item.reviewStatus === 'false_positive'
}

export function filterOcrItems(items: OcrItem[], filters: ResultFilters): OcrItem[] {
  const term = filters.search.trim().toLowerCase()
  const activeThreshold = filters.minimumConfidence > 0
    ? filters.minimumConfidence
    : filters.lowConfidenceThreshold
  return items.filter(item => {
    if (item.reviewStatus === 'deleted' && !filters.showDeleted) return false
    if (item.reviewStatus === 'false_positive' && !filters.showFalsePositive) return false
    if (filters.lowOnly ? item.score >= activeThreshold : item.score < filters.minimumConfidence) return false
    return !term || (item.corrected || item.text).toLowerCase().includes(term)
  })
}

export function exportableOcrItems(items: OcrItem[]): OcrItem[] {
  return items.filter(item => !isExcludedFromExport(item))
}

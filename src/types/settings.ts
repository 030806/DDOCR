import type { ExportMode } from '../exportResults'
import type { ResultViewMode } from '../ocrLayout'

export type AppSettings = {
  defaultModelId: string
  lowConfidenceThreshold: number
  defaultResultViewMode: ResultViewMode
  showConfidence: boolean
  defaultExportMode: ExportMode
  defaultZoom: number
}

export const DEFAULT_APP_SETTINGS: AppSettings = {
  defaultModelId: 'steel-v2',
  lowConfidenceThreshold: 0.95,
  defaultResultViewMode: 'list',
  showConfidence: true,
  defaultExportMode: 'simple',
  defaultZoom: 0.82,
}

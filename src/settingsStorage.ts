import { DEFAULT_APP_SETTINGS, type AppSettings } from './types/settings'

export const SETTINGS_STORAGE_KEY = 'ddocr.settings.v1'

const modelIds = new Set(['general-v4', 'steel-v2', 'invoice-v3'])

export function normalizeSettings(value: unknown): AppSettings {
  const candidate = value && typeof value === 'object' ? value as Partial<AppSettings> : {}
  return {
    defaultModelId: typeof candidate.defaultModelId === 'string' && modelIds.has(candidate.defaultModelId) ? candidate.defaultModelId : DEFAULT_APP_SETTINGS.defaultModelId,
    lowConfidenceThreshold: typeof candidate.lowConfidenceThreshold === 'number' && candidate.lowConfidenceThreshold >= 0.5 && candidate.lowConfidenceThreshold <= 1 ? candidate.lowConfidenceThreshold : DEFAULT_APP_SETTINGS.lowConfidenceThreshold,
    defaultResultViewMode: candidate.defaultResultViewMode === 'layout' ? 'layout' : 'list',
    showConfidence: typeof candidate.showConfidence === 'boolean' ? candidate.showConfidence : DEFAULT_APP_SETTINGS.showConfidence,
    defaultExportMode: candidate.defaultExportMode === 'full' ? 'full' : 'simple',
    defaultZoom: typeof candidate.defaultZoom === 'number' && candidate.defaultZoom >= 0.55 && candidate.defaultZoom <= 3 ? candidate.defaultZoom : DEFAULT_APP_SETTINGS.defaultZoom,
  }
}

export function parseStoredSettings(raw: string | null) {
  if (!raw) return { ...DEFAULT_APP_SETTINGS }
  try { return normalizeSettings(JSON.parse(raw)) } catch { return { ...DEFAULT_APP_SETTINGS } }
}

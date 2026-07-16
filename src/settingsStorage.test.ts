import { describe, expect, it } from 'vitest'
import { parseStoredSettings } from './settingsStorage'
import { DEFAULT_APP_SETTINGS } from './types/settings'

describe('application settings storage', () => {
  it('restores valid saved settings', () => {
    const settings = parseStoredSettings(JSON.stringify({ defaultModelId: 'general-v4', lowConfidenceThreshold: 0.88, defaultResultViewMode: 'layout', showConfidence: false, defaultExportMode: 'full', defaultZoom: 1 }))
    expect(settings).toMatchObject({ defaultModelId: 'general-v4', lowConfidenceThreshold: 0.88, defaultResultViewMode: 'layout', showConfidence: false, defaultExportMode: 'full', defaultZoom: 1 })
  })

  it('falls back safely for malformed or out-of-range values', () => {
    expect(parseStoredSettings('{bad json')).toEqual(DEFAULT_APP_SETTINGS)
    expect(parseStoredSettings(JSON.stringify({ lowConfidenceThreshold: 2, defaultZoom: 4 }))).toMatchObject({ lowConfidenceThreshold: 0.95, defaultZoom: 0.82 })
  })
})

import { describe, it, expect } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import IlluminationSelect from './IlluminationSelect.vue'
import type { IlluminationMode } from '../types/ocr'

describe('illumination choice', () => {
  it.each<IlluminationMode>(['none', 'he', 'clahe'])('renders all choices and restores %s', async (modelValue) => {
    const html = await renderToString(createSSRApp(IlluminationSelect, { modelValue }))
    expect(html).toContain('光照处理')
    expect(html).toContain('原图')
    expect(html).toContain('全局 HE')
    expect(html).toContain('CLAHE')
    expect(html).toContain(`<select value="${modelValue}"`)
  })

  it('locks the selector while saving or recognizing', async () => {
    const html = await renderToString(createSSRApp(IlluminationSelect, { modelValue: 'he', disabled: true }))
    expect(html).toMatch(/<select[^>]*disabled/)
  })
})

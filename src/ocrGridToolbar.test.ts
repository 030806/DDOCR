import { describe, it, expect } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import OcrResultGrid from './components/OcrResultGrid.vue'

async function render(statuses: Record<string, string> = {}) {
  const app = createSSRApp(OcrResultGrid, {
    rows: [], selectedId: '', selectedIds: [], values: () => ({}), statuses,
    revision: 0, canUndo: false, canRedo: false,
  })
  app.component('a-modal', { render: () => null })
  return renderToString(app)
}
describe('compact OCR grid toolbar', () => {
  it('hides idle save counts and keeps accessible disabled history controls', async () => {
    const html = await render()
    expect(html).not.toContain('ocr-grid-save-status')
    expect(html).toMatch(/disabled[^>]*aria-label="撤销"/)
    expect(html).toContain('操作帮助</summary>')
    expect(html).not.toContain('<details class="ocr-grid-help" open')
    expect(html).toContain('放大表格')
  })
  it('shows saving and failure counts and offers retry for failed saves', async () => {
    const html = await render({ a: '保存中', b: '保存失败：断网', c: '版本冲突', d: '已保存' })
    expect(html).toContain('正在保存 1 行')
    expect(html).toContain('2 行失败或冲突')
    expect(html).toContain('重试失败项')
  })
  it('requires review rather than offering bulk retry for conflicts alone', async () => {
    const html = await render({ a: '版本冲突' })
    expect(html).toContain('1 行失败或冲突')
    expect(html).not.toContain('重试失败项')
    expect(html).not.toContain('正在保存')
  })
})

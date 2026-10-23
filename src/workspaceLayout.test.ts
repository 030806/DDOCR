import { describe, it, expect, vi, afterEach } from 'vitest'
import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createRouter, createMemoryHistory } from 'vue-router'
import DocumentViewer from './components/DocumentViewer.vue'
import AppHeader from './components/AppHeader.vue'

vi.mock('./components/BBoxLayer.vue', () => ({ default: { render: () => null } }))
vi.mock('./components/UserMenu.vue', () => ({ default: { render: () => null } }))

const props = { pages: [], page: { no: 1, label: 'drawing.png', items: [] }, currentPage: 1, selectedId: '', zoom: 1, jobState: 'done' as const, progress: 100 }
afterEach(() => vi.unstubAllGlobals())
describe('workspace layout', () => {
  it('restores collapsed page navigation while retaining image controls', async () => {
    vi.stubGlobal('localStorage', { getItem: () => 'true' })
    const html = await renderToString(createSSRApp(DocumentViewer, props))
    expect(html).toContain('aria-expanded="false"')
    expect(html).toContain('aria-expanded="false"')
    expect(html).toContain('展开页面栏')
    expect(html).toContain('zoom-buttons')
    expect(html).toContain('drawing.png')
  })
  it('keeps navigation expanded when storage is unavailable', async () => {
    vi.stubGlobal('localStorage', { getItem: () => { throw new Error('denied') } })
    const html = await renderToString(createSSRApp(DocumentViewer, props))
    expect(html).toContain('aria-expanded="true"')
    expect(html).toContain('收起页面栏')
  })
  it('shows workspace navigation on terminal tasks', async () => {
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/terminal-tasks', component: { template: '<div />' } }] })
    await router.push('/terminal-tasks')
    const app = createSSRApp(AppHeader)
    app.use(router)
    const html = await renderToString(app)
    expect(html).toMatch(/<button[^>]*>工作台<\/button>/)
  })
})

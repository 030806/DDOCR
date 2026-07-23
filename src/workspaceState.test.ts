import { describe, expect, it } from 'vitest'
import { createEmptyWorkspaceContent } from './workspaceState'

describe('workspace initial state', () => {
  it('starts without mock pages or a selected OCR result', () => {
    expect(createEmptyWorkspaceContent()).toEqual({
      pages: [],
      currentPage: 1,
      selectedId: '',
    })
  })

  it('returns an isolated page collection for each workspace visit', () => {
    const first = createEmptyWorkspaceContent()
    const second = createEmptyWorkspaceContent()

    expect(first.pages).not.toBe(second.pages)
  })
})

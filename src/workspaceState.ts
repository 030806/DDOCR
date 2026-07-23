import type { OcrPage } from './types/ocr'

export type WorkspaceContent = {
  pages: OcrPage[]
  currentPage: number
  selectedId: string
}

export function createEmptyWorkspaceContent(): WorkspaceContent {
  return { pages: [], currentPage: 1, selectedId: '' }
}

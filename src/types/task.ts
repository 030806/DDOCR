export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed'

export type OcrTask = {
  id: string
  name: string
  fileName: string
  fileType: 'PDF' | 'PNG' | 'JPG'
  createdAt: string
  modelId: string
  modelName: string
  pageCount: number
  status: TaskStatus
  durationMs: number | null
  regionCount: number
  reviewCount: number
  mockPageNumbers: number[]
}

export type TaskTimeOrder = 'newest' | 'oldest'

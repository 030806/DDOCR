export type TaskStatus = 'queued' | 'running' | 'succeeded' | 'partial' | 'failed'

export type OcrJobStatus =
  | 'queued'
  | 'running'
  | 'recognizing'
  | 'persisting'
  | 'partial_success'
  | 'succeeded'
  | 'failed'
  | 'cancelled'

export type OcrTask = {
  id: string
  name: string
  fileName: string
  fileType: 'PDF' | 'PNG' | 'JPG'
  createdAt: string
  modelId: string
  modelVersion?: string
  modelName: string
  pageCount: number
  status: TaskStatus
  jobStatus?: OcrJobStatus
  stage?: string
  progress?: number
  startedAt?: string | null
  finishedAt?: string | null
  errorCode?: string | null
  errorMessage?: string | null
  durationMs: number | null
  regionCount: number
  reviewCount: number
  mockPageNumbers: number[]
}

export type TaskTimeOrder = 'newest' | 'oldest'

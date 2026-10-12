export type OcrComment = {
  id: string
  authorId?: string
  author: string
  content: string
  time: string
  updatedAt?: string | null
}

export type OcrPolygon = [
  [number, number],
  [number, number],
  [number, number],
  [number, number],
]

export type OcrItem = {
  id: string
  text: string
  score: number
  bbox: [number, number, number, number]
  polygon?: OcrPolygon
  revision?: number
  corrected?: string
  comments: OcrComment[]
  reviewStatus?: OcrReviewStatus
  editSource?: 'ocr' | 'manual'
  geometryRevision?: number
  terminalNumber?: string
  manualConfirmed?: boolean
  tableNote?: string
  tableRevision?: number
  needsRawTextReview?: boolean
}

export type OcrReviewStatus = 'unreviewed' | 'confirmed' | 'false_positive' | 'deleted'

export type TerminalPoint = {
  id: string
  x: number
  y: number
  source: 'model' | 'manual'
  score?: number
}

export type OcrPage = {
  no: number
  label: string
  items: OcrItem[]
  imageUrl?: string
  sourceWidth?: number
  sourceHeight?: number
  terminalPoints?: TerminalPoint[] | null
  terminalModelCount?: number | null
  terminalError?: { code: string; message: string } | null
  terminalRevision?: number
}

export type ModelOption = {
  value: string
  version: string
  label: string
  note: string
  speed: string
}

export type OcrComment = {
  id: string
  authorId?: string
  author: string
  content: string
  time: string
  updatedAt?: string | null
}

export type OcrItem = {
  id: string
  text: string
  score: number
  bbox: [number, number, number, number]
  revision?: number
  corrected?: string
  comments: OcrComment[]
}

export type OcrPage = {
  no: number
  label: string
  items: OcrItem[]
  imageUrl?: string
  sourceWidth?: number
  sourceHeight?: number
}

export type ModelOption = {
  value: string
  version: string
  label: string
  note: string
  speed: string
}

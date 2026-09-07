import { describe, expect, it } from 'vitest'
import { isPreviewableImage, MAX_UPLOAD_SIZE_BYTES } from './imageUpload'

describe('image upload helpers', () => {
  it('uses a 200 MiB upload limit', () => {
    expect(MAX_UPLOAD_SIZE_BYTES).toBe(209_715_200)
  })

  it('only marks images as rotatable previews', () => {
    expect(isPreviewableImage(new File([], 'terminal.png', { type: 'image/png' }))).toBe(true)
    expect(isPreviewableImage(new File([], 'drawing.pdf', { type: 'application/pdf' }))).toBe(false)
  })
})

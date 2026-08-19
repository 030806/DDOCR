export const MAX_UPLOAD_SIZE_BYTES = 200 * 1024 * 1024

export function isPreviewableImage(file: File): boolean {
  return file.type.startsWith('image/')
}

export async function rotateImageFile(file: File, degrees: number): Promise<File> {
  const normalized = ((degrees % 360) + 360) % 360
  if (!normalized) return file

  const bitmap = await createImageBitmap(file)
  const swapSides = normalized === 90 || normalized === 270
  const canvas = document.createElement('canvas')
  canvas.width = swapSides ? bitmap.height : bitmap.width
  canvas.height = swapSides ? bitmap.width : bitmap.height
  const context = canvas.getContext('2d')
  if (!context) throw new Error('Canvas is unavailable')

  context.translate(canvas.width / 2, canvas.height / 2)
  context.rotate(normalized * Math.PI / 180)
  context.drawImage(bitmap, -bitmap.width / 2, -bitmap.height / 2)
  bitmap.close()

  const outputType = file.type === 'image/png' ? 'image/png' : 'image/jpeg'
  const blob = await new Promise<Blob>((resolve, reject) => {
    canvas.toBlob(value => value ? resolve(value) : reject(new Error('Image conversion failed')), outputType, .95)
  })
  return new File([blob], file.name, { type: outputType, lastModified: Date.now() })
}

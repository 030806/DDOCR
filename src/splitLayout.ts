export type SplitLayout = {
  documentMinPercent: number
  resultMinPercent: number
  documentSizePercent: number
  resultSizePercent: number
}

export function createSplitLayout(containerWidth: number): SplitLayout {
  const safeWidth = Math.max(containerWidth, 1)
  const resultWidth = safeWidth <= 1350 ? 350 : 390
  const resultSizePercent = (resultWidth / safeWidth) * 100

  return {
    documentMinPercent: (400 / safeWidth) * 100,
    resultMinPercent: (300 / safeWidth) * 100,
    documentSizePercent: 100 - resultSizePercent,
    resultSizePercent,
  }
}

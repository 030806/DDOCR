import type { RegionDraft } from './api/ocr'

export const MAX_OCR_REGIONS = 20
export const MIN_OCR_REGION_SIZE = 16

export function regionBboxFromPoints(
  first: [number, number], second: [number, number], width: number, height: number,
): RegionDraft['bbox'] | undefined {
  const clamp = (value: number, maximum: number) => Math.min(maximum, Math.max(0, value))
  const bbox: RegionDraft['bbox'] = [
    Math.round(clamp(Math.min(first[0], second[0]), width)),
    Math.round(clamp(Math.min(first[1], second[1]), height)),
    Math.round(clamp(Math.max(first[0], second[0]), width)),
    Math.round(clamp(Math.max(first[1], second[1]), height)),
  ]
  if (bbox[2] - bbox[0] < MIN_OCR_REGION_SIZE || bbox[3] - bbox[1] < MIN_OCR_REGION_SIZE) return undefined
  return bbox
}

export function copyRegions(regions: RegionDraft[]): RegionDraft[] {
  return regions.map(region => ({ clientId: region.clientId, bbox: [...region.bbox] }))
}

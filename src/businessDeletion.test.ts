import { expect, it } from 'vitest'
import { selectedBusinessSourceIds } from './businessDeletion'

it('maps selected business rows to unique active OCR sources', () => {
  const records = [
    { id: 'terminal:a', sourceResultId: 'ocr-1' },
    { id: 'terminal:b', sourceResultId: null },
    { id: 'ocr:ocr-2', sourceResultId: 'ocr-2' },
    { id: 'terminal:c', sourceResultId: 'ocr-1' },
  ]
  expect(selectedBusinessSourceIds(records, ['terminal:a', 'terminal:b', 'ocr:ocr-2', 'terminal:c'], ['ocr-1']))
    .toEqual(['ocr-1'])
  expect(selectedBusinessSourceIds(records, ['terminal:b'], ['ocr-1', 'ocr-2'])).toEqual([])
})

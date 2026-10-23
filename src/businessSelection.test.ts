import { expect, it } from 'vitest'
import { businessSelection } from './businessSelection'
it('selects both the terminal point and OCR source for a populated row', () => {
 expect(businessSelection({terminalPointId:'p7',sourceResultId:'ocr8',cable:'X18B2'})).toEqual({pointId:'p7',sourceId:'ocr8'})
})
it('clears irrelevant highlights for empty and unmatched rows', () => {
 expect(businessSelection({terminalPointId:'p7',sourceResultId:'ocr8',cable:''})).toEqual({pointId:'p7',sourceId:''})
 expect(businessSelection({terminalPointId:null,sourceResultId:'ocr8',cable:'X18B2'})).toEqual({pointId:'',sourceId:'ocr8'})
 expect(businessSelection({terminalPointId:'p7',sourceResultId:'ocr8',cable:'X',sourceUnavailable:true})).toEqual({pointId:'p7',sourceId:''})
})

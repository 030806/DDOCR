import { describe, expect, it } from 'vitest'
import { terminalNumberFillValues } from './terminalNumberFill'
import type { OcrItem } from './types/ocr'

const item = (id: string, terminalNumber = ''): OcrItem => ({
  id, terminalNumber, text: id, score: 1, bbox: [0, 0, 20, 20], comments: [],
})

describe('terminal number one-click fill', () => {
  it('fills selected blank rows using their displayed row numbers', () => {
    const values = terminalNumberFillValues([item('a'), item('b'), item('c')], ['a', 'c'])
    expect([...values]).toEqual([['a', '1'], ['c', '3']])
  })

  it('does not overwrite an existing terminal number', () => {
    const values = terminalNumberFillValues([item('a', 'X1'), item('b')], ['a', 'b'])
    expect([...values]).toEqual([['b', '2']])
  })
})

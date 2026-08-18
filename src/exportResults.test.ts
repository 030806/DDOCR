import { describe, expect, it } from 'vitest'
import { createFullExportRows, createSimpleExportRows } from './exportResults'
import type { OcrItem } from './mock'

const items: OcrItem[] = [
  {
    id: '1', text: 'QF10I', corrected: 'QF101', score: 0.9, bbox: [0, 0, 10, 10],
    comments: [
      { id: 'c1', author: '张三', content: '字符I误识别', time: '10:00' },
      { id: 'c2', author: '李四', content: '已复核', time: '10:02' },
    ],
  },
  { id: '2', text: 'X23', score: 0.98, bbox: [10, 10, 20, 20], comments: [] },
]

describe('OCR Excel export rows', () => {
  it('exports only the final result in simple mode', () => {
    expect(createSimpleExportRows(items)).toEqual([
      { 编号: '01', 端子排最终识别结果: 'QF101' },
      { 编号: '02', 端子排最终识别结果: 'X23' },
    ])
  })

  it('expands each comment into an individual full export row', () => {
    const rows = createFullExportRows(items)
    expect(rows).toHaveLength(3)
    expect(rows[0]).toMatchObject({ 编号: '01', 原始识别结果: 'QF10I', 纠正结果: 'QF101', 最终识别结果: 'QF101', 留言人: '张三', 留言结果: '字符I误识别' })
    expect(rows[1]).toMatchObject({ 编号: '01', 留言人: '李四', 留言结果: '已复核' })
  })

  it('keeps one row with blank review fields when there are no comments', () => {
    expect(createFullExportRows(items)[2]).toEqual({ 编号: '02', 原始识别结果: 'X23', 纠正结果: '', 最终识别结果: 'X23', 留言人: '', 留言结果: '' })
  })

  it('does not export deleted or false-positive results', () => {
    const excluded = [
      { ...items[0], reviewStatus: 'deleted' as const },
      { ...items[1], reviewStatus: 'false_positive' as const },
    ]
    expect(createSimpleExportRows(excluded)).toEqual([])
    expect(createFullExportRows(excluded)).toEqual([])
  })
})

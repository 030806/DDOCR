import { afterEach, describe, expect, it, vi } from 'vitest'
import { TERMINAL_CREATE_PROMPT, filterTerminalRows, readPendingSides, terminalRowStatus, terminalSidePath, writePendingSides } from './terminalState'
import type { TerminalRow } from './api/terminal'
afterEach(() => vi.unstubAllGlobals())

describe('terminal navigation and review filters', () => {
  it('provides the create-task guidance shown on the terminal task page', () => {
    expect(TERMINAL_CREATE_PROMPT).toBe('填写名称创建新的端子排任务')
  })
  it('retains an unfinished side while visiting another tab, and isolates tasks', () => {
    const values = new Map<string, string>()
    vi.stubGlobal('sessionStorage', { getItem: (key: string) => values.get(key), setItem: (key: string, value: string) => values.set(key, value) })
    writePendingSides('a', { left: 'pending-job' })
    expect(readPendingSides('a')).toEqual({ left: 'pending-job' })
    expect(readPendingSides('b')).toEqual({})
    writePendingSides('a', {})
    expect(readPendingSides('a')).toEqual({})
  })
  it('keeps task identity and side in single-image routes', () => {
    expect(terminalSidePath('strip', 'right', 'job')).toBe('/terminal-tasks/strip/right/job')
    expect(terminalSidePath('strip', 'left')).toBe('/terminal-tasks/strip/left')
  })
  it('does not hide unconfirmed missing-side or conflicting rows', () => {
    const rows = [
      { id: 'a', confirmed: true, conflict: false, left: {}, right: {} },
      { id: 'b', confirmed: false, conflict: true, left: {}, right: null },
      { id: 'c', confirmed: false, conflict: false, left: null, right: {} },
    ] as TerminalRow[]
    expect(filterTerminalRows(rows, 'pending').map(r => r.id)).toEqual(['b', 'c'])
    expect(filterTerminalRows(rows, 'confirmed').map(r => r.id)).toEqual(['a'])
    expect(terminalRowStatus(rows[1])).toBe('编号缺失或重复')
    expect(terminalRowStatus(rows[2])).toBe('缺左侧')
  })
})

import { describe, expect, it, vi } from 'vitest'
import { runDatasetBatch } from './datasetBatch'
import type { DatasetStatus } from './api/dataset'

const reviewed = (id: string): DatasetStatus => ({ job_id: id, state: 'reviewed', result_version: 2, reviewed_version: 2, reviewed_at: null, saved_version: null, image_id: null, last_error: null })

describe('batch dataset publication', () => {
  it('continues after a failure and reports each task separately', async () => {
    const save = vi.fn().mockResolvedValueOnce({ ...reviewed('a'), state: 'saved' }).mockRejectedValueOnce(new Error('disk')).mockResolvedValueOnce({ ...reviewed('c'), state: 'saved' })
    const report = vi.fn()
    const result = await runDatasetBatch(['a', 'b', 'c'].map(reviewed), report, save)
    expect(result.map(item => item.success)).toEqual([true, false, true])
    expect(report).toHaveBeenCalledTimes(3)
    expect(save.mock.calls.map(call => call[0])).toEqual(['a', 'b', 'c'])
  })
  it('skips unreviewed and already saved tasks', async () => {
    const save = vi.fn()
    const result = await runDatasetBatch([{ ...reviewed('a'), state: 'unreviewed' }, { ...reviewed('b'), state: 'saved' }], vi.fn(), save)
    expect(save).not.toHaveBeenCalled()
    expect(result.every(item => !item.success)).toBe(true)
  })
  it('does not report a changed version as currently saved', async () => {
    const save = vi.fn().mockResolvedValue({ ...reviewed('a'), state: 'unreviewed' })
    const [result] = await runDatasetBatch([reviewed('a')], vi.fn(), save)
    expect(result?.success).toBe(false)
  })
  it('waits for the current publication before starting the next', async () => {
    let release!: (status: DatasetStatus) => void
    const save = vi.fn().mockImplementationOnce(() => new Promise<DatasetStatus>(resolve => { release = resolve })).mockResolvedValue({ ...reviewed('b'), state: 'saved' })
    const running = runDatasetBatch([reviewed('a'), reviewed('b')], vi.fn(), save)
    expect(save).toHaveBeenCalledTimes(1)
    release({ ...reviewed('a'), state: 'saved' })
    await running
    expect(save).toHaveBeenCalledTimes(2)
  })
})

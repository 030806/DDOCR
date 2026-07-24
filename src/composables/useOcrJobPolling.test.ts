import { afterEach, describe, expect, it, vi } from 'vitest'
import type { OcrTask } from '../types/task'
import { useOcrJobPolling } from './useOcrJobPolling'

function task(jobStatus: OcrTask['jobStatus'], progress: number): OcrTask {
  return {
    id: 'job-1', name: 'sample', fileName: 'sample.png', fileType: 'PNG',
    createdAt: '2026-07-24T00:00:00Z', modelId: 'terminal', modelVersion: '1', modelName: 'terminal · 1',
    pageCount: 1, status: jobStatus === 'succeeded' ? 'succeeded' : 'running', jobStatus,
    stage: jobStatus, progress, startedAt: null, finishedAt: null, errorCode: null, errorMessage: null,
    durationMs: null, regionCount: 0, reviewCount: 0, mockPageNumbers: [1],
  }
}

afterEach(() => vi.useRealTimers())

describe('useOcrJobPolling', () => {
  it('polls every second and stops after success', async () => {
    vi.useFakeTimers()
    const fetchTask = vi.fn()
      .mockResolvedValueOnce(task('queued', 0))
      .mockResolvedValueOnce(task('recognizing', 50))
      .mockResolvedValueOnce(task('succeeded', 100))
    const onSucceeded = vi.fn()
    const polling = useOcrJobPolling({ fetchTask })

    polling.start('job-1', { onSucceeded })
    await vi.advanceTimersByTimeAsync(0)
    expect(fetchTask).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(2000)

    expect(fetchTask).toHaveBeenCalledTimes(3)
    expect(onSucceeded).toHaveBeenCalledOnce()
    expect(polling.polling.value).toBe(false)
  })

  it('stops and exposes a failed task', async () => {
    vi.useFakeTimers()
    const failed = { ...task('failed', 42), errorCode: 'ENGINE_ERROR', errorMessage: 'boom' }
    const onFailed = vi.fn()
    const polling = useOcrJobPolling({ fetchTask: vi.fn().mockResolvedValue(failed) })

    polling.start('job-1', { onFailed })
    await vi.advanceTimersByTimeAsync(0)

    expect(onFailed).toHaveBeenCalledWith(failed)
    expect(polling.task.value?.errorCode).toBe('ENGINE_ERROR')
    expect(polling.polling.value).toBe(false)
  })

  it('stop cancels the next timer', async () => {
    vi.useFakeTimers()
    const fetchTask = vi.fn().mockResolvedValue(task('running', 10))
    const polling = useOcrJobPolling({ fetchTask })
    polling.start('job-1')
    await vi.advanceTimersByTimeAsync(0)
    polling.stop()
    await vi.advanceTimersByTimeAsync(3000)
    expect(fetchTask).toHaveBeenCalledOnce()
  })
})

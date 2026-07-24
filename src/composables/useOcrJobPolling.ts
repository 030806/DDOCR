import { computed, ref } from 'vue'
import { getTask } from '../api/ocr'
import type { OcrTask } from '../types/task'

export type OcrJobPollingCallbacks = {
  onUpdate?: (task: OcrTask) => void
  onSucceeded?: (task: OcrTask) => void
  onFailed?: (task: OcrTask) => void
}

export type OcrJobPollingOptions = {
  intervalMs?: number
  fetchTask?: (jobId: string) => Promise<OcrTask>
}

const successfulStatuses = new Set(['succeeded', 'partial_success'])
const failedStatuses = new Set(['failed', 'cancelled'])

export function useOcrJobPolling(options: OcrJobPollingOptions = {}) {
  const task = ref<OcrTask>()
  const polling = ref(false)
  const requestError = ref<unknown>()
  const now = ref(Date.now())
  const intervalMs = options.intervalMs ?? 1000
  const fetchTask = options.fetchTask ?? getTask
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0

  const elapsedMs = computed(() => {
    if (!task.value) return 0
    if (task.value.durationMs !== null) return task.value.durationMs
    const start = Date.parse(task.value.startedAt || task.value.createdAt)
    const end = task.value.finishedAt ? Date.parse(task.value.finishedAt) : now.value
    return Number.isFinite(start) && Number.isFinite(end) ? Math.max(0, end - start) : 0
  })

  function stop(): void {
    generation += 1
    polling.value = false
    if (timer !== undefined) clearTimeout(timer)
    timer = undefined
  }

  function start(jobId: string, callbacks: OcrJobPollingCallbacks = {}): void {
    stop()
    const currentGeneration = generation
    polling.value = true
    requestError.value = undefined

    const poll = async (): Promise<void> => {
      try {
        const latest = await fetchTask(jobId)
        if (currentGeneration !== generation) return
        task.value = latest
        now.value = Date.now()
        requestError.value = undefined
        callbacks.onUpdate?.(latest)

        if (latest.jobStatus && successfulStatuses.has(latest.jobStatus)) {
          stop()
          callbacks.onSucceeded?.(latest)
          return
        }
        if (latest.jobStatus && failedStatuses.has(latest.jobStatus)) {
          stop()
          callbacks.onFailed?.(latest)
          return
        }
      } catch (error) {
        if (currentGeneration !== generation) return
        requestError.value = error
      }

      if (currentGeneration === generation) timer = setTimeout(poll, intervalMs)
    }

    void poll()
  }

  function reset(): void {
    stop()
    task.value = undefined
    requestError.value = undefined
  }

  return { task, polling, requestError, elapsedMs, start, stop, reset }
}

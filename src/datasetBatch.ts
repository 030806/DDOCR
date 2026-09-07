import { isAxiosError } from 'axios'
import { datasetButton, saveDatasetEntry, type DatasetStatus } from './api/dataset'

export type BatchOutcome = { jobId: string; success: boolean; message: string }

export async function runDatasetBatch(
  jobs: DatasetStatus[],
  onResult: (outcome: BatchOutcome, status?: DatasetStatus) => void,
  save = saveDatasetEntry,
): Promise<BatchOutcome[]> {
  const outcomes: BatchOutcome[] = []
  for (const job of jobs) {
    let outcome: BatchOutcome
    let updated: DatasetStatus | undefined
    if (datasetButton(job).disabled || job.reviewed_version == null) {
      outcome = { jobId: job.job_id, success: false, message: '当前任务不可入库，请刷新复核状态' }
    } else {
      try {
        updated = await save(job.job_id, job.reviewed_version)
        outcome = { jobId: job.job_id, success: updated.state === 'saved', message: updated.state === 'saved' ? '已入库' : '已保存旧版本，当前修改需重新复核' }
      } catch (error) {
        outcome = { jobId: job.job_id, success: false, message: isAxiosError(error) ? error.response?.data?.error?.message || '入库未完成，请刷新状态后重试' : '入库失败，请重试' }
      }
    }
    outcomes.push(outcome)
    onResult(outcome, updated)
  }
  return outcomes
}

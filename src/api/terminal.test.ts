import { afterEach, expect, it, vi } from 'vitest'
import { apiClient } from './client'
import { associateSide, reviewTerminalRows, linkTerminalRows, createTerminalTask, deleteTerminalTask, type TerminalTask } from './terminal'
afterEach(() => vi.restoreAllMocks())
const task = { id: 'strip', revision: 3, version: 'source-version' } as TerminalTask
it('associates an explicit page and preserves optimistic revision', async () => {
  const put = vi.spyOn(apiClient, 'put').mockResolvedValue({ data: { data: task } })
  await associateSide(task, 'right', 'job', 2)
  expect(put).toHaveBeenCalledWith('/terminal-tasks/strip/sides/right', { job_id: 'job', page_no: 2, base_revision: 3 }, expect.anything())
})
it('review and manual pairing send the source version', async () => {
  const patch = vi.spyOn(apiClient, 'patch').mockResolvedValue({ data: { data: task } })
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { data: task } })
  await reviewTerminalRows(task, [{ id: 'r', confirmed: true, note: 'checked' }])
  await linkTerminalRows(task, 'left-result', null)
  expect(patch.mock.calls[0][1]).toEqual({ base_revision: 3, version: 'source-version', rows: [{ id: 'r', confirmed: true, note: 'checked' }] })
  expect(post.mock.calls[0][1]).toEqual({ base_revision: 3, version: 'source-version', left: 'left-result', right: null })
})
it('creation retries can reuse the same idempotency key', async () => {
  const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { data: task } })
  await createTerminalTask('X1', 'stable-key')
  expect(post).toHaveBeenCalledWith('/terminal-tasks', { name: 'X1' }, { headers: { 'Idempotency-Key': 'stable-key' } })
})
it('deletes a terminal task with its current revision', async () => {
  const remove = vi.spyOn(apiClient, 'delete').mockResolvedValue({ status: 204 } as never)
  await deleteTerminalTask(task)
  expect(remove).toHaveBeenCalledWith('/terminal-tasks/strip', { headers: { 'If-Match': '"3"' } })
})

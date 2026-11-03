import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'
import { createRegionOcrTask, rerunOcrTask, uploadAndCreateOcrTaskFromSelection, type RegionDraft } from './ocr'
import type { IlluminationMode } from '../types/ocr'

afterEach(() => vi.restoreAllMocks())
const model = { value: 'mock', version: '1.0.0' }
describe.each<IlluminationMode>(['none', 'he', 'clahe'])('explicit %s illumination', mode => {
  it.each([false, true])('passes the selected mode through upload, regions=%s', async selected => {
    const post = vi.spyOn(apiClient, 'post')
      .mockResolvedValueOnce({ data: { data: { file_id: 'file1', upload_headers: {} } } })
      .mockResolvedValueOnce({ data: { data: { id: 'file1' } } })
      .mockResolvedValueOnce({ data: { data: { id: 'job1' } } })
    vi.spyOn(apiClient, 'put').mockResolvedValue({})
    const regions: RegionDraft[] = selected ? [{ clientId: 'r1', bbox: [10, 10, 100, 100] }] : []
    await uploadAndCreateOcrTaskFromSelection(new File(['image'], 'terminal.png'), model, regions, undefined, mode)
    expect(post).toHaveBeenLastCalledWith(selected ? '/ocr/region-jobs' : '/ocr/jobs', expect.objectContaining({ illumination: mode }))
  })
  it('passes the selected mode for reruns and source region tasks', async () => {
    const post = vi.spyOn(apiClient, 'post').mockResolvedValue({ data: { data: { id: 'job1' } } })
    await rerunOcrTask('source', model, mode)
    expect(post).toHaveBeenLastCalledWith('/ocr/jobs/source/rerun', expect.objectContaining({ illumination: mode }))
    await createRegionOcrTask({ name: 'region', sourceJobId: 'source', model, illumination: mode, regions: [{ clientId: 'r1', bbox: [10, 10, 100, 100] }] })
    expect(post).toHaveBeenLastCalledWith('/ocr/region-jobs', expect.objectContaining({ illumination: mode }))
  })
})

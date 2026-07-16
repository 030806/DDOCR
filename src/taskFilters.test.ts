import { describe, expect, it } from 'vitest'
import { mockTasks } from './mock/tasks'
import { filterAndSortTasks } from './taskFilters'

describe('task history filters', () => {
  it('searches by task name and file name', () => {
    expect(filterAndSortTasks(mockTasks, '铭牌', 'all', 'newest').map((task) => task.id)).toEqual(['task-plate-0713'])
    expect(filterAndSortTasks(mockTasks, 'packing_list', 'all', 'newest').map((task) => task.id)).toEqual(['task-pack-0712'])
  })

  it('filters tasks by status', () => {
    expect(filterAndSortTasks(mockTasks, '', 'failed', 'newest')).toHaveLength(1)
  })

  it('sorts tasks by creation time', () => {
    expect(filterAndSortTasks(mockTasks, '', 'all', 'newest')[0].id).toBe('task-qc-0714')
    expect(filterAndSortTasks(mockTasks, '', 'all', 'oldest')[0].id).toBe('task-terminal-0709')
  })
})

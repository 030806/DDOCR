import type { OcrTask, TaskStatus, TaskTimeOrder } from './types/task'

export function filterAndSortTasks(tasks: OcrTask[], search: string, status: TaskStatus | 'all', order: TaskTimeOrder) {
  const term = search.trim().toLocaleLowerCase()
  return tasks
    .filter((task) => !term || task.name.toLocaleLowerCase().includes(term) || task.fileName.toLocaleLowerCase().includes(term))
    .filter((task) => status === 'all' || task.status === status)
    .sort((left, right) => {
      const difference = new Date(left.createdAt).getTime() - new Date(right.createdAt).getTime()
      return order === 'oldest' ? difference : -difference
    })
}

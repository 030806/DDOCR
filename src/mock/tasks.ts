import type { OcrTask } from '../types/task'

export const mockTasks: OcrTask[] = [
  { id: 'task-qc-0714', name: '轴承套圈质量复核', fileName: 'QC_Report_0714.pdf', fileType: 'PDF', createdAt: '2026-07-15T09:42:18+08:00', modelId: 'steel-v2', modelName: '钢材铭牌专用 · V2', pageCount: 3, status: 'partial', durationMs: 1840, regionCount: 31, reviewCount: 4, mockPageNumbers: [1, 2, 3] },
  { id: 'task-plate-0713', name: '二号线设备铭牌抽检', fileName: 'VMC_850L_plate.png', fileType: 'PNG', createdAt: '2026-07-14T16:25:03+08:00', modelId: 'steel-v2', modelName: '钢材铭牌专用 · V2', pageCount: 1, status: 'succeeded', durationMs: 620, regionCount: 6, reviewCount: 0, mockPageNumbers: [2] },
  { id: 'task-pack-0712', name: '出口设备装箱单识别', fileName: 'packing_list_A17.pdf', fileType: 'PDF', createdAt: '2026-07-13T11:08:46+08:00', modelId: 'general-v4', modelName: '通用文字检测 · V4', pageCount: 3, status: 'succeeded', durationMs: 2290, regionCount: 24, reviewCount: 1, mockPageNumbers: [1, 2, 3] },
  { id: 'task-terminal-0711', name: '端子排编号批次 26-0711', fileName: 'terminal_batch_0711.jpg', fileType: 'JPG', createdAt: '2026-07-12T18:36:29+08:00', modelId: 'general-v4', modelName: '通用文字检测 · V4', pageCount: 1, status: 'failed', durationMs: null, regionCount: 0, reviewCount: 0, mockPageNumbers: [1] },
  { id: 'task-invoice-0710', name: '供应商到货票据归档', fileName: 'supplier_invoice_0710.pdf', fileType: 'PDF', createdAt: '2026-07-11T14:17:52+08:00', modelId: 'invoice-v3', modelName: '工业票据识别 · V3', pageCount: 8, status: 'running', durationMs: null, regionCount: 86, reviewCount: 7, mockPageNumbers: [1, 2, 3] },
  { id: 'task-terminal-0709', name: '控制柜端子标识巡检', fileName: 'cabinet_B08.png', fileType: 'PNG', createdAt: '2026-07-10T08:55:11+08:00', modelId: 'steel-v2', modelName: '钢材铭牌专用 · V2', pageCount: 1, status: 'queued', durationMs: null, regionCount: 0, reviewCount: 0, mockPageNumbers: [3] },
]

export function findMockTask(taskId: string) {
  return mockTasks.find((task) => task.id === taskId)
}

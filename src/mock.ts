import type { ModelOption, OcrItem, OcrPage } from './types/ocr'

export type { ModelOption, OcrItem }
export type MockPage = OcrPage

export const models: ModelOption[] = [
  { value: 'general-v4', version: '4', label: '通用文字检测 · V4', note: '中英文 / 印刷体', speed: '38 ms/页' },
  { value: 'steel-v2', version: '2', label: '钢材铭牌专用 · V2', note: '低对比度 / 喷码', speed: '52 ms/页' },
  { value: 'invoice-v3', version: '3', label: '工业票据识别 · V3', note: '表格 / 数字增强', speed: '64 ms/页' },
]

export const pages: MockPage[] = [
  {
    no: 1,
    label: '质量检验报告',
    items: [
      { id: 'r-101', text: '产品质量检验报告', score: 0.998, bbox: [120, 64, 515, 112], comments: [] },
      { id: 'r-102', text: 'QUALITY INSPECTION REPORT', score: 0.992, bbox: [156, 119, 480, 144], comments: [] },
      { id: 'r-103', text: '产品名称：精密轴承套圈', score: 0.974, bbox: [74, 204, 360, 234], comments: [] },
      { id: 'r-104', text: '报告编号：QI-2026-0714', score: 0.986, bbox: [374, 204, 645, 234], comments: [] },
      { id: 'r-105', text: '检测项目', score: 0.997, bbox: [78, 286, 180, 318], comments: [] },
      { id: 'r-106', text: '标准要求', score: 0.995, bbox: [250, 286, 352, 318], comments: [] },
      { id: 'r-107', text: '实测结果', score: 0.993, bbox: [412, 286, 514, 318], comments: [] },
      { id: 'r-108', text: '判定', score: 0.998, bbox: [580, 286, 630, 318], comments: [] },
      { id: 'r-109', text: '外径尺寸', score: 0.982, bbox: [78, 348, 176, 380], comments: [] },
      { id: 'r-110', text: 'Φ62.00 ±0.02 mm', score: 0.941, bbox: [240, 348, 380, 380], comments: [] },
      { id: 'r-111', text: '62.01 mm', score: 0.965, bbox: [424, 348, 506, 380], comments: [] },
      { id: 'r-112', text: '合格', score: 0.997, bbox: [584, 348, 628, 380], comments: [] },
      { id: 'r-113', text: '表面粗糙度', score: 0.978, bbox: [78, 414, 195, 446], comments: [] },
      { id: 'r-114', text: 'Ra ≤ 0.8 μm', score: 0.884, bbox: [240, 414, 350, 446], comments: [{ id: 'c-1', author: '陈工', content: '原件此处反光，请复核单位。', time: '10:32' }] },
      { id: 'r-115', text: 'Ra 0.63 μm', score: 0.936, bbox: [424, 414, 520, 446], comments: [] },
      { id: 'r-116', text: '合格', score: 0.996, bbox: [584, 414, 628, 446], comments: [] },
      { id: 'r-117', text: '检验结论：本批次产品符合技术规范要求，准予入库。', score: 0.968, bbox: [74, 516, 625, 552], comments: [] },
      { id: 'r-118', text: '检验员：LJ-042', score: 0.927, bbox: [76, 650, 220, 682], comments: [] },
      { id: 'r-119', text: '日期：2026年07月14日', score: 0.989, bbox: [420, 650, 625, 682], comments: [] },
    ],
  },
  {
    no: 2,
    label: '设备铭牌',
    items: [
      { id: 'r-201', text: '高精度数控加工中心', score: 0.993, bbox: [130, 105, 565, 152], comments: [] },
      { id: 'r-202', text: '型号 MODEL：VMC-850L', score: 0.971, bbox: [112, 238, 520, 278], comments: [] },
      { id: 'r-203', text: '额定功率：18.5 kW', score: 0.948, bbox: [112, 318, 460, 358], comments: [] },
      { id: 'r-204', text: '出厂编号：CN26071408', score: 0.902, bbox: [112, 398, 500, 438], comments: [] },
      { id: 'r-205', text: '制造日期：2026-06', score: 0.986, bbox: [112, 478, 440, 518], comments: [] },
      { id: 'r-206', text: '中国 · 苏州', score: 0.995, bbox: [230, 618, 455, 658], comments: [] },
    ],
  },
  {
    no: 3,
    label: '装箱清单',
    items: [
      { id: 'r-301', text: '装箱清单 PACKING LIST', score: 0.996, bbox: [136, 72, 560, 116], comments: [] },
      { id: 'r-302', text: '主机组件 × 1', score: 0.987, bbox: [96, 240, 300, 274], comments: [] },
      { id: 'r-303', text: '标准刀柄 × 12', score: 0.976, bbox: [96, 310, 320, 344], comments: [] },
      { id: 'r-304', text: '随机工具箱 × 1', score: 0.991, bbox: [96, 380, 320, 414], comments: [] },
      { id: 'r-305', text: '技术资料 × 2册', score: 0.955, bbox: [96, 450, 330, 484], comments: [] },
      { id: 'r-306', text: '复核：WH-018', score: 0.933, bbox: [440, 650, 610, 682], comments: [] },
    ],
  },
]

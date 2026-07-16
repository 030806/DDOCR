<script setup lang="ts">
import { computed } from 'vue'
import type { MockPage } from '../mock'

const props = defineProps<{
  page: MockPage
  selectedId: string
  zoom: number
}>()

const emit = defineEmits<{ select: [id: string] }>()
const stageConfig = computed(() => ({ width: 700 * props.zoom, height: 760 * props.zoom, scaleX: props.zoom, scaleY: props.zoom }))

function scoreColor(score: number, active = false) {
  if (active) return '#ffb94e'
  if (score < 0.90) return '#ef5350'
  if (score < 0.95) return '#42a5f5'
  return '#66bb6a'
}
</script>

<template>
  <v-stage :config="stageConfig">
    <v-layer>
      <v-rect :config="{ x: 0, y: 0, width: 700, height: 760, fill: '#fbfaf6', shadowColor: '#0b1512', shadowBlur: 25, shadowOpacity: .2, shadowOffsetY: 8 }" />
      <v-rect :config="{ x: 50, y: 38, width: 8, height: 78, fill: '#168b6c' }" />
      <v-text :config="{ x: 74, y: 40, text: page.no === 1 ? 'JUXI PRECISION' : page.no === 2 ? 'JUXI MACHINERY' : 'JUXI LOGISTICS', fontSize: 13, fontStyle: 'bold', fill: '#168b6c', letterSpacing: 2 }" />
      <v-line :config="{ points: [50, 170, 650, 170], stroke: '#d9d7cf', strokeWidth: 1 }" />
      <v-line v-for="y in [274, 336, 402, 468]" :key="y" :config="{ points: [64, y, 640, y], stroke: '#e4e2da', strokeWidth: 1 }" />
      <v-line v-for="x in [218, 398, 554]" :key="x" :config="{ points: [x, 274, x, 468], stroke: '#e4e2da', strokeWidth: 1 }" />
      <v-text v-for="item in page.items" :key="`text-${item.id}`" :config="{ x: item.bbox[0] + 2, y: item.bbox[1] + 5, text: item.corrected || item.text, fontSize: Math.min(25, Math.max(13, item.bbox[3] - item.bbox[1] - 9)), fontStyle: item.id === page.items[0].id ? 'bold' : 'normal', fill: '#252c29', width: item.bbox[2] - item.bbox[0], ellipsis: true }" />
    </v-layer>
    <v-layer>
      <v-group v-for="item in page.items" :key="item.id" @click="emit('select', item.id)" @tap="emit('select', item.id)">
        <v-rect :config="{ x: item.bbox[0], y: item.bbox[1], width: item.bbox[2] - item.bbox[0], height: item.bbox[3] - item.bbox[1], stroke: scoreColor(item.score, selectedId === item.id), strokeWidth: selectedId === item.id ? 3 : 1.5, fill: selectedId === item.id ? 'rgba(255,185,78,.12)' : 'rgba(53,199,153,.035)', cornerRadius: 2, hitStrokeWidth: 12 }" />
        <v-label :config="{ x: item.bbox[0], y: item.bbox[1] - 18, opacity: selectedId === item.id ? 1 : .84 }">
          <!-- <v-tag :config="{ fill: scoreColor(item.score, selectedId === item.id), cornerRadius: [3,3,0,0] }" /> -->
          <!-- <v-text :config="{ text: `${index + 1}  ${Math.round(item.score * 100)}%`, fontSize: 10, padding: 4, fill: '#10201b', fontStyle: 'bold' }" /> -->
        </v-label>
      </v-group>
    </v-layer>
  </v-stage>
</template>

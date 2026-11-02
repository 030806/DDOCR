import type { RouteRecordRaw } from 'vue-router'

export const terminalTaskChildren: RouteRecordRaw[] = [
  { path: '', redirect: to => `${to.path}/left` },
  { path: 'merged', name: 'terminal-merged', component: { render: () => null } },
  { path: ':side(left|right)/workflow', name: 'terminal-side-workflow', component: () => import('./views/TerminalSideView.vue') },
  { path: ':side(left|right)', name: 'terminal-side-entry', component: () => import('./views/TerminalSideView.vue') },
  { path: ':side(left|right)/:taskId', name: 'terminal-side', component: () => import('./views/WorkspaceView.vue') },
]

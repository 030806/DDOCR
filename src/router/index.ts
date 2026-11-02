import { createRouter, createWebHistory } from 'vue-router'
import { terminalTaskChildren } from '../terminalTaskRoutes'
import { AUTH_TOKEN_KEY } from '../api/auth'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/workspace' },
    { path: '/auth', name: 'auth', component: () => import('../views/AuthView.vue') },
    { path: '/workspace', name: 'workspace', component: () => import('../views/WorkspaceView.vue') },
    { path: '/workspace/:taskId', name: 'workspace-task', component: () => import('../views/WorkspaceView.vue') },
    { path: '/terminal-workflow', name: 'terminal-workflow', component: () => import('../features/terminal-workflow/TerminalWorkflowView.vue') },
    { path: '/tasks', name: 'tasks', component: () => import('../views/TaskHistoryView.vue') },
    { path: '/terminal-tasks', name: 'terminal-tasks', component: () => import('../views/TerminalTasksView.vue') },
    {
      path: '/terminal-tasks/:terminalId', component: () => import('../views/TerminalTaskView.vue'),
      children: terminalTaskChildren,
    },
  ],
})

router.beforeEach((to) => {
  const authenticated = Boolean(window.localStorage.getItem(AUTH_TOKEN_KEY))
  if (to.name !== 'auth' && !authenticated) return { name: 'auth' }
  if (to.name === 'auth' && authenticated) return { name: 'workspace' }
})

export default router

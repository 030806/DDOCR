import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/workspace' },
    { path: '/workspace', name: 'workspace', component: () => import('../views/WorkspaceView.vue') },
    { path: '/workspace/:taskId', name: 'workspace-task', component: () => import('../views/WorkspaceView.vue') },
    { path: '/tasks', name: 'tasks', component: () => import('../views/TaskHistoryView.vue') },
  ],
})

export default router

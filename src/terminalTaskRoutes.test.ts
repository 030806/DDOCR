import { describe, it, expect } from 'vitest'
import { createRouter, createMemoryHistory } from 'vue-router'
import { terminalTaskChildren } from './terminalTaskRoutes'

const router=createRouter({history:createMemoryHistory(),routes:[{path:'/terminal-tasks/:terminalId',component:{render:()=>null},children:terminalTaskChildren}]})
describe('task-owned side routes',()=>{
  it.each(['left','right'])('keeps %s workflow and results inside the task shell',side=>{
    const entry=router.resolve(`/terminal-tasks/task-a/${side}`)
    expect(entry.name).toBe('terminal-side-entry')
    expect(entry.matched).toHaveLength(2)
    const flow=router.resolve(`/terminal-tasks/task-a/${side}/workflow`)
    expect(flow.name).toBe('terminal-side-workflow')
    expect(flow.params.taskId).toBeUndefined()
    expect(flow.params.terminalId).toBe('task-a')
    expect(router.resolve(`/terminal-tasks/task-a/${side}/job-a`).name).toBe('terminal-side')
  })
  it('keeps merged results in the same shell',()=>{
    expect(router.resolve('/terminal-tasks/task-a/merged').name).toBe('terminal-merged')
  })
})

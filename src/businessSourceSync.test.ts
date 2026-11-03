import {describe,it,expect} from 'vitest'
import {planTableSync} from './businessSourceSync'
import type {TerminalRecord} from './api/terminalDocument'
const row=(id:string,sourceResultId:string|null):TerminalRecord=>({id,sourceResultId,terminalPointId:id,terminalNumber:'1',cable:'OLD',manual:false,manualConfirmed:false,tableNote:'',sourceRevision:0})
const item={id:'ocr',text:'OLD',bbox:[0,0,10,10] as [number,number,number,number],score:1,comments:[],revision:2,tableRevision:3}
describe('table source synchronization plan',()=>{
 it('uses stable source IDs and separate text/number fields',()=>{
   const a=row('b','ocr'), plan=planTableSync([a],[{...a,cable:'NEW',terminalNumber:'A'}],[item])
   expect(plan.updates).toEqual([{result_id:'ocr',base_revision:2,base_table_revision:3,text:'NEW',terminal_number:'A'}])
   expect(plan.shared.size).toBe(0)
 })
 it('skips no-source rows and clipboard reassociations',()=>{
   const a=row('b',null)
   expect(planTableSync([a],[{...a,cable:'NEW'}],[item]).skipped).toBe(1)
   expect(planTableSync([a],[{...a,sourceResultId:'ocr',cable:'NEW'}],[item]).updates).toEqual([])
 })
 it('requires a shared-source decision and rejects conflicting batch edits',()=>{
   const a=row('a','ocr'),b=row('b','ocr')
   expect(planTableSync([a,b],[{...a,cable:'NEW'},b],[item]).shared.has('ocr')).toBe(true)
   expect(()=>planTableSync([a,b],[{...a,cable:'NEW'},{...b,cable:'DIFFERENT'}],[item])).toThrow('不同值')
 })
})

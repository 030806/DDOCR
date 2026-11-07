import {it,expect} from 'vitest'
import {createSSRApp} from 'vue'
import {renderToString} from '@vue/server-renderer'
import Controls from './components/TerminalResultControls.vue'
it('exposes enhancement rerun without generic upload or model replacement',async()=>{
 const app=createSSRApp(Controls,{fileName:'terminal.jpg',illumination:'none',busy:false})
 app.component('a-button',{template:'<button><slot /></button>'})
 const html=await renderToString(app)
 expect(html).toContain('沿用已确认的文字区域、骨架、起始端子及编号规则')
 expect(html).toContain('按已确认配置重新识别')
 expect(html).not.toContain('type="file"')
 expect(html).not.toContain('替换文件')
 expect(html).not.toContain('识别模型')
})

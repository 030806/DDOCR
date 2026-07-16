import { createApp } from 'vue'
import Antd from 'ant-design-vue'
import VueKonva from 'vue-konva'
import 'ant-design-vue/dist/reset.css'
import './style.css'
import App from './App.vue'
import router from './router'

createApp(App).use(Antd).use(VueKonva).use(router).mount('#app')

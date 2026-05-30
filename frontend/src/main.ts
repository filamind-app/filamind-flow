import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import './assets/styles/main.css'
import { registerWidgets } from './widgets'

const app = createApp(App)
app.use(createPinia())

// Feature widgets self-register here. The scaffold ships with none.
registerWidgets()

app.mount('#app')

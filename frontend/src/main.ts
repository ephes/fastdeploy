import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import HelloWorldVue from './components/HelloWorld.vue'


const routes = [
    { path: '/', component: App },
    { path: '/hello/:msg', name: 'hello', component: HelloWorldVue},
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

const app = createApp(App)
app.use(router)
app.config.globalProperties.$router = router
app.mount('#app')

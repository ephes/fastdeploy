import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

import { createClient } from './client'
import Login from './components/Login.vue'
import HelloWorldVue from './components/HelloWorld.vue'
import Home from './components/Home.vue'
import DeploymentVue from './components/Deployment.vue'


const routes = [
    { path: '/', component: Home },
    { path: '/login', component: Login},
    { path: '/hello', component: HelloWorldVue},
    { path: '/deployment', component: DeploymentVue},
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

const client = createClient()
const app = createApp(App)
app.use(router)
app.use(client)
app.mount('#app')

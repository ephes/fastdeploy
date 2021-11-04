import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'

import { createClient } from './client'
import Login from './components/Login.vue'
import HelloWorldVue from './components/HelloWorld.vue'
import Home from './components/Home.vue'
import Services from './components/Services.vue'
import DeploymentVue from './components/Deployment.vue'


const client = createClient()

const routes = [
    { path: '/', component: Services },
    { path: '/login', name: 'login', component: Login },
    { path: '/hello', component: HelloWorldVue },
    { path: '/deployment', component: DeploymentVue },
]

const router = createRouter({
    history: createWebHistory(),
    routes,
})

router.beforeEach((to, from) => {
    console.log("beforeEach: ", client.isAuthenticated.value, to, from)
    if (!client.isAuthenticated.value && to.name !== 'login') {
        // redirect to login if not authenticated
        return { name: "login" }
    } else {
        return true
    }
})

const app = createApp(App)
app.use(router)
app.use(client)
app.mount('#app')

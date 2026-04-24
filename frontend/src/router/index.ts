import { createRouter, createWebHistory } from 'vue-router'
import WorkbenchView from '../views/WorkbenchView.vue'
import SkillLibraryView from '../views/SkillLibraryView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: WorkbenchView },
    { path: '/workspace/:taskId', component: WorkbenchView },
    { path: '/skills', component: SkillLibraryView },
  ]
})

export default router

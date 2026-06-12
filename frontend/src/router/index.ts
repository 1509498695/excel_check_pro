import { createRouter, createWebHistory } from 'vue-router'

import { useAuthStore } from '../store/auth'
import { routeComponents } from './routePreload'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: routeComponents.login,
      meta: { guest: true },
    },
    {
      path: '/register',
      name: 'register',
      component: routeComponents.register,
      meta: { guest: true },
    },
    {
      path: '/',
      name: 'main-board',
      component: routeComponents.mainBoard,
      meta: { auth: true },
    },
    {
      path: '/fixed-rules',
      name: 'fixed-rules-board',
      component: routeComponents.fixedRules,
      meta: { auth: true },
    },
    {
      path: '/rule-configs',
      name: 'rule-configs',
      component: routeComponents.ruleConfigs,
      meta: { auth: true },
    },
    {
      path: '/rule-configs/config_lookup',
      redirect: { name: 'rule-configs' },
    },
    {
      path: '/rule-configs/config_lookup/:ruleId',
      name: 'rule-config-lookup',
      component: routeComponents.ruleConfigLookup,
      meta: { auth: true, activeNav: 'rule-configs' },
    },
    {
      path: '/admin',
      name: 'admin',
      component: routeComponents.admin,
      meta: { auth: true, admin: true },
    },
    {
      path: '/profile',
      name: 'profile',
      component: routeComponents.profile,
      meta: { auth: true },
    },
    {
      path: '/user-guide',
      name: 'user-guide',
      component: routeComponents.userGuide,
      meta: { auth: true, activeNav: 'profile' },
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  if (!auth.isReady) {
    await auth.fetchMe()
  }

  if (to.meta.auth && !auth.isLoggedIn) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.guest && auth.isLoggedIn) {
    return { name: 'main-board' }
  }

  if (to.meta.admin && !auth.isProjectAdmin) {
    return { name: 'main-board' }
  }
})

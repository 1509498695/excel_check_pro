const viewLoaders = {
  login: () => import('../views/LoginView.vue'),
  register: () => import('../views/RegisterView.vue'),
  mainBoard: () => import('../views/MainBoard.vue'),
  fixedRules: () => import('../views/FixedRulesBoard.vue'),
  ruleConfigs: () => import('../views/RuleConfigsView.vue'),
  ruleConfigLookup: () => import('../views/RuleConfigLookupView.vue'),
  testCases: () => import('../views/TestCaseGeneratorView.vue'),
  admin: () => import('../views/AdminView.vue'),
  profile: () => import('../views/ProfileView.vue'),
  userGuide: () => import('../views/UserGuideView.vue'),
}

export const routeComponents = {
  login: viewLoaders.login,
  register: viewLoaders.register,
  mainBoard: viewLoaders.mainBoard,
  fixedRules: viewLoaders.fixedRules,
  ruleConfigs: viewLoaders.ruleConfigs,
  ruleConfigLookup: viewLoaders.ruleConfigLookup,
  testCases: viewLoaders.testCases,
  admin: viewLoaders.admin,
  profile: viewLoaders.profile,
  userGuide: viewLoaders.userGuide,
}

export function preloadRouteComponent(path: string): void {
  const normalizedPath = path.split('?')[0]?.split('#')[0] || '/'

  if (normalizedPath === '/fixed-rules') {
    void viewLoaders.fixedRules()
    return
  }

  if (normalizedPath === '/rule-configs') {
    void viewLoaders.ruleConfigs()
    return
  }

  if (
    normalizedPath === '/rule-configs/config_lookup' ||
    normalizedPath.startsWith('/rule-configs/config_lookup/')
  ) {
    void viewLoaders.ruleConfigLookup()
    return
  }

  if (normalizedPath === '/test-cases') {
    void viewLoaders.testCases()
    return
  }

  if (normalizedPath === '/admin') {
    void viewLoaders.admin()
    return
  }

  if (normalizedPath === '/profile') {
    void viewLoaders.profile()
    return
  }

  if (normalizedPath === '/user-guide') {
    void viewLoaders.userGuide()
    return
  }

  if (normalizedPath === '/register') {
    void viewLoaders.register()
    return
  }

  void viewLoaders.mainBoard()
}

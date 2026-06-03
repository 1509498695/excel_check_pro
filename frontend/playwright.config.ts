import { defineConfig, devices } from '@playwright/test'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const frontendRoot = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(frontendRoot, '..')
const e2eRuntimeRoot = resolve(projectRoot, '.e2e-runtime')
const backendPort = process.env.E2E_BACKEND_PORT || '18080'
const frontendPort = process.env.E2E_FRONTEND_PORT || '15173'
const backendUrl = `http://127.0.0.1:${backendPort}`
const frontendUrl = `http://127.0.0.1:${frontendPort}`
const pythonCommand = process.env.E2E_PYTHON || 'python'

function sqliteUrl(filePath: string): string {
  return `sqlite+aiosqlite:///${filePath.replace(/\\/g, '/')}`
}

export default defineConfig({
  testDir: './tests/e2e',
  testMatch: '**/*.e2e.ts',
  fullyParallel: false,
  workers: 1,
  timeout: 90_000,
  expect: {
    timeout: 15_000,
  },
  reporter: [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: frontendUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: [
    {
      command: `${pythonCommand} backend/run.py`,
      cwd: projectRoot,
      url: `${backendUrl}/health`,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        APP_ENV: 'development',
        APP_HOST: '127.0.0.1',
        APP_PORT: backendPort,
        CORS_ALLOW_ORIGINS: frontendUrl,
        DB_URL: sqliteUrl(resolve(e2eRuntimeRoot, 'backend', 'excel_check_e2e.db')),
        DEFAULT_SUPER_ADMIN_PASSWORD: '123456',
        ENABLE_LOCAL_PICKER: 'false',
        JWT_SECRET_KEY: 'e2e-local-jwt-secret-key',
        RUNTIME_DIR: resolve(e2eRuntimeRoot, 'backend', 'runtime'),
        RUNTIME_UPLOAD_DIR: resolve(e2eRuntimeRoot, 'backend', 'uploads', 'local_excel'),
        SVN_CACHE_DIR: resolve(e2eRuntimeRoot, 'backend', 'svn-cache'),
        SVN_URL_ALLOWLIST: 'samosvn',
      },
    },
    {
      command: `npm run dev -- --host 127.0.0.1 --port ${frontendPort}`,
      cwd: frontendRoot,
      url: frontendUrl,
      timeout: 120_000,
      reuseExistingServer: false,
      env: {
        ...process.env,
        VITE_API_PROXY_TARGET: backendUrl,
      },
    },
  ],
})

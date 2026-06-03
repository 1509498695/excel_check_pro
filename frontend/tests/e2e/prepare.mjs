import { mkdir, rm } from 'node:fs/promises'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const e2eRoot = dirname(fileURLToPath(import.meta.url))
const projectRoot = resolve(e2eRoot, '..', '..', '..')
const runtimeRoot = resolve(projectRoot, '.e2e-runtime')

await rm(runtimeRoot, { recursive: true, force: true })
await mkdir(resolve(runtimeRoot, 'backend'), { recursive: true })

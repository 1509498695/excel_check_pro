// @vitest-environment happy-dom

import { describe, expect, it } from 'vitest'

import { router } from '../../src/router'

describe('test case generator route', () => {
  it('registers the static test case generator page as an authenticated route', () => {
    const route = router.getRoutes().find((item) => item.name === 'test-cases')

    expect(route?.path).toBe('/test-cases')
    expect(route?.meta.auth).toBe(true)
  })
})

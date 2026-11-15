import { describe, expect, it } from 'vitest'
import App from './App.tsx'

describe('App', () => {
  it('is a component', () => {
    expect(typeof App).toBe('function')
  })
})

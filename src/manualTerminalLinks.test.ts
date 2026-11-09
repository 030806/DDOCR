import { expect, it } from 'vitest'
import { connectTerminalLink } from './manualTerminalLinks'

it('reassigns a detected line from terminal 7 to terminal 6 without duplicating it', () => {
  const previous = { '7': 'line-6', '6': 'line-old' }
  const next = connectTerminalLink(previous, '6', 'line-6')
  expect(next).toEqual({ '6': 'line-6' })
  expect(previous).toEqual({ '7': 'line-6', '6': 'line-old' })
})

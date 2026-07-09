import { describe, expect, it } from 'vitest'

import { countDiffLines } from './diffStats'

describe('countDiffLines', () => {
  it('counts added and removed lines while ignoring file headers', () => {
    expect(
      countDiffLines('--- a/base.md\n+++ b/base.md\n context\n-old line\n+new line\n+second line'),
    ).toEqual({ added: 2, removed: 1 })
  })

  it('handles empty input', () => {
    expect(countDiffLines('')).toEqual({ added: 0, removed: 0 })
  })

  it('handles addition-only and deletion-only diffs', () => {
    expect(countDiffLines('+++ b/base.md\n+added')).toEqual({ added: 1, removed: 0 })
    expect(countDiffLines('--- a/base.md\n-removed')).toEqual({ added: 0, removed: 1 })
  })

  it('does not count header-only diffs', () => {
    expect(countDiffLines('--- a/base.md\n+++ b/base.md')).toEqual({ added: 0, removed: 0 })
  })
})

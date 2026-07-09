export type DiffLineStats = {
  added: number
  removed: number
}

export function countDiffLines(diffText: string): DiffLineStats {
  let added = 0
  let removed = 0

  for (const line of diffText.split(/\r?\n/)) {
    if (line.startsWith('+++') || line.startsWith('---')) {
      continue
    }
    if (line.startsWith('+')) {
      added += 1
    } else if (line.startsWith('-')) {
      removed += 1
    }
  }

  return { added, removed }
}

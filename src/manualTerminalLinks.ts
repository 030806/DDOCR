export function connectTerminalLink(links: Record<string, string>, pointId: string, sourceId: string): Record<string, string> {
  const next = { ...links }
  for (const [point, source] of Object.entries(next)) if (source === sourceId) delete next[point]
  next[pointId] = sourceId
  return next
}

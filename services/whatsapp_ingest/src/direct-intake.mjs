export function parseDirectProjectDirective(value) {
  const text = String(value || '').trim()
  if (!text) return null
  const match = text.match(/^proyecto\s*:\s*(.+)$/iu)
  if (!match) return null
  const projectHint = match[1].trim().replace(/\s+/g, ' ')
  if (!projectHint || projectHint.length > 160) return null
  return { projectHint }
}

export function isDirectCliDirective(value) {
  return /^cli$/iu.test(String(value || '').trim())
}

export function isDirectChat(jid) {
  return String(jid || '').endsWith('@s.whatsapp.net')
    || String(jid || '').endsWith('@lid')
}

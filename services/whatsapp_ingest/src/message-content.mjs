const WRAPPER_KEYS = [
  'ephemeralMessage',
  'viewOnceMessage',
  'viewOnceMessageV2',
  'viewOnceMessageV2Extension',
  'documentWithCaptionMessage',
]

export function unwrapMessageContent(message) {
  let current = message
  for (let depth = 0; depth < 8 && current; depth += 1) {
    let nested = null
    for (const key of WRAPPER_KEYS) {
      if (current[key]?.message) {
        nested = current[key].message
        break
      }
    }
    if (!nested) return current
    current = nested
  }
  return current || null
}

export function parseInboundContent(message) {
  const content = unwrapMessageContent(message)
  if (!content) return null

  const text = firstNonEmptyString(
    content.conversation,
    content.extendedTextMessage?.text,
    content.imageMessage?.caption,
    content.videoMessage?.caption,
    content.documentMessage?.caption,
  )

  if (content.audioMessage) {
    return {
      kind: 'audio',
      media: content.audioMessage,
      mimeType: content.audioMessage.mimetype || 'audio/ogg',
      seconds: integerValue(content.audioMessage.seconds),
      text,
      voiceNote: Boolean(content.audioMessage.ptt),
    }
  }

  if (text) {
    return {
      kind: 'text',
      media: null,
      mimeType: null,
      seconds: null,
      text,
      voiceNote: false,
    }
  }

  return null
}

export function timestampSeconds(value) {
  if (typeof value === 'number') return Math.trunc(value)
  if (typeof value === 'bigint') return Number(value)
  if (value && typeof value.toNumber === 'function') return value.toNumber()
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null
}

function firstNonEmptyString(...values) {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) return value.trim()
  }
  return null
}

function integerValue(value) {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? Math.trunc(parsed) : null
}

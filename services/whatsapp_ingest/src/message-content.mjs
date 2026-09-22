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

  if (content.imageMessage) {
    return {
      kind: 'image',
      media: content.imageMessage,
      mimeType: content.imageMessage.mimetype || 'image/jpeg',
      seconds: null,
      text,
      voiceNote: false,
    }
  }

  if (isPdfDocument(content.documentMessage)) {
    return {
      kind: 'document',
      media: content.documentMessage,
      mimeType: content.documentMessage.mimetype || 'application/pdf',
      fileName: content.documentMessage.fileName || null,
      seconds: null,
      text,
      voiceNote: false,
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

function isPdfDocument(document) {
  if (!document) return false
  const mimeType = String(document.mimetype || '').split(';', 1)[0].trim().toLowerCase()
  const fileName = String(document.fileName || '').trim().toLowerCase()
  return mimeType === 'application/pdf' || fileName.endsWith('.pdf')
}

export function parseSharedContacts(message) {
  const content = unwrapMessageContent(message)
  if (!content) return []
  const candidates = []
  if (content.contactMessage) candidates.push(content.contactMessage)
  if (Array.isArray(content.contactsArrayMessage?.contacts)) {
    candidates.push(...content.contactsArrayMessage.contacts)
  }
  const contacts = []
  for (const candidate of candidates) {
    const phone = phoneFromVcard(candidate?.vcard)
    if (!phone) continue
    contacts.push({
      displayName: String(candidate?.displayName || nameFromVcard(candidate?.vcard) || '').trim() || null,
      phone,
    })
  }
  return contacts
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

function phoneFromVcard(value) {
  const vcard = String(value || '')
  const waid = vcard.match(/(?:^|;)waid=(\d{8,15})(?:[;:])/im)?.[1]
  if (waid) return `+${waid}`
  for (const line of vcard.split(/\r?\n/)) {
    if (!/^TEL(?:;|:)/i.test(line)) continue
    const digits = String(line.split(':').slice(1).join(':')).replace(/\D/g, '')
    if (digits.length >= 8 && digits.length <= 15) return `+${digits}`
  }
  return null
}

function nameFromVcard(value) {
  for (const line of String(value || '').split(/\r?\n/)) {
    if (!/^FN(?:;|:)/i.test(line)) continue
    return line.split(':').slice(1).join(':').replace(/\\([,;])/g, '$1').trim() || null
  }
  return null
}

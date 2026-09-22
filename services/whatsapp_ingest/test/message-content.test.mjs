import assert from 'node:assert/strict'
import test from 'node:test'

import {
  parseInboundContent,
  parseSharedContacts,
  timestampSeconds,
  unwrapMessageContent,
} from '../src/message-content.mjs'

test('parses plain and extended text messages', () => {
  assert.deepEqual(parseInboundContent({ conversation: ' hola ' }), {
    kind: 'text',
    media: null,
    mimeType: null,
    seconds: null,
    text: 'hola',
    voiceNote: false,
  })
  assert.equal(parseInboundContent({ extendedTextMessage: { text: 'detalle' } }).text, 'detalle')
})

test('unwraps ephemeral audio and preserves voice note metadata', () => {
  const wrapped = {
    ephemeralMessage: {
      message: {
        audioMessage: { mimetype: 'audio/ogg; codecs=opus', ptt: true, seconds: 12 },
      },
    },
  }
  assert.ok(unwrapMessageContent(wrapped).audioMessage)
  assert.deepEqual(parseInboundContent(wrapped), {
    kind: 'audio',
    media: wrapped.ephemeralMessage.message.audioMessage,
    mimeType: 'audio/ogg; codecs=opus',
    seconds: 12,
    text: null,
    voiceNote: true,
  })
})

test('parses images with and without captions', () => {
  const image = { mimetype: 'image/png', caption: 'Revisar esta pantalla' }
  assert.deepEqual(parseInboundContent({ imageMessage: image }), {
    kind: 'image',
    media: image,
    mimeType: 'image/png',
    seconds: null,
    text: 'Revisar esta pantalla',
    voiceNote: false,
  })
  assert.deepEqual(parseInboundContent({ imageMessage: {} }), {
    kind: 'image',
    media: {},
    mimeType: 'image/jpeg',
    seconds: null,
    text: null,
    voiceNote: false,
  })
})

test('parses PDF documents with their original filename and caption', () => {
  const document = {
    mimetype: 'application/pdf',
    fileName: 'Informe técnico.pdf',
    caption: 'Revisar este informe',
  }
  assert.deepEqual(parseInboundContent({ documentMessage: document }), {
    kind: 'document',
    media: document,
    mimeType: 'application/pdf',
    fileName: 'Informe técnico.pdf',
    seconds: null,
    text: 'Revisar este informe',
    voiceNote: false,
  })
  assert.equal(parseInboundContent({
    documentMessage: { mimetype: 'application/octet-stream', fileName: 'plano.pdf' },
  }).kind, 'document')
})

test('ignores unsupported protocol-only messages', () => {
  assert.equal(parseInboundContent({ protocolMessage: { type: 0 } }), null)
})

test('extracts WhatsApp numbers from individual and array contact cards', () => {
  assert.deepEqual(parseSharedContacts({
    contactMessage: {
      displayName: 'Mariano Muratore',
      vcard: 'BEGIN:VCARD\nTEL;type=CELL;waid=5491155552000:+54 9 11 5555-2000\nEND:VCARD',
    },
  }), [{ displayName: 'Mariano Muratore', phone: '+5491155552000' }])
  assert.deepEqual(parseSharedContacts({
    contactsArrayMessage: {
      contacts: [{
        vcard: 'BEGIN:VCARD\nFN:Mariano Muratore\nTEL;TYPE=CELL:+54 9 11 5555-2000\nEND:VCARD',
      }],
    },
  }), [{ displayName: 'Mariano Muratore', phone: '+5491155552000' }])
})

test('normalizes protobuf-style timestamps', () => {
  assert.equal(timestampSeconds(123), 123)
  assert.equal(timestampSeconds(123n), 123)
  assert.equal(timestampSeconds({ toNumber: () => 456 }), 456)
})

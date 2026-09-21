import assert from 'node:assert/strict'
import test from 'node:test'

import { parseInboundContent, timestampSeconds, unwrapMessageContent } from '../src/message-content.mjs'

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

test('ignores unsupported protocol-only messages', () => {
  assert.equal(parseInboundContent({ protocolMessage: { type: 0 } }), null)
})

test('normalizes protobuf-style timestamps', () => {
  assert.equal(timestampSeconds(123), 123)
  assert.equal(timestampSeconds(123n), 123)
  assert.equal(timestampSeconds({ toNumber: () => 456 }), 456)
})

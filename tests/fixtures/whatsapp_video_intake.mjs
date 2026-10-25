// Offline input at the Baileys boundary. No WhatsApp socket or credentials.
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { parseInboundContent, downloadInboundMedia } from '../../services/whatsapp_ingest/src/message-content.mjs'
import { IntakeStore } from '../../services/whatsapp_ingest/src/store.mjs'

const [dataDir, videoPath, mode, asDocument, caption] = process.argv.slice(2)
const store = new IntakeStore(dataDir)
await store.initialize()
const receivedAt = new Date('2026-10-05T12:00:00Z')
const common = { source: 'whatsapp-direct', group_id: 'laboratory',
  whatsapp_timestamp: receivedAt.toISOString(), received_at: receivedAt.toISOString() }
await store.persist({ project: 'direct-bruno', receivedAt,
  manifest: { ...common, message_id: '01-route', kind: 'text',
    text: mode === 'cli' ? 'CLI' : 'Proyecto: example' } })
const message = { message: { [asDocument === 'yes' ? 'documentMessage' : 'videoMessage']:
  { mimetype: 'video/mp4', fileName: 'test.mp4', seconds: 1, caption } } }
const parsed = parseInboundContent(message.message)
assert.equal(parsed.kind, 'video')
const mediaBuffer = await downloadInboundMedia(message, parsed, async (input) => {
  assert.equal(input, message)
  return readFile(videoPath)
})
await store.persist({ project: 'direct-bruno', receivedAt, mediaBuffer,
  manifest: { ...common, message_id: '02-video', kind: parsed.kind, text: parsed.text,
    mime_type: parsed.mimeType, video_seconds: parsed.seconds, original_filename: parsed.fileName } })

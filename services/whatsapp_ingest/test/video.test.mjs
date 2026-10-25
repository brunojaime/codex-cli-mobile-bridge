import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { parseInboundContent, downloadInboundMedia } from '../src/message-content.mjs'
import { IntakeStore, extensionForMime } from '../src/store.mjs'

for (const caption of [undefined, 'Revisar este recorrido']) {
  for (const asDocument of [false, true]) {
    test(`video intake preserves media, caption and duration (${asDocument}, ${caption})`, async (t) => {
      const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-video-'))
      t.after(() => rm(root, { recursive: true, force: true }))
      const media = { mimetype: 'video/mp4', seconds: 3, caption, fileName: 'recorrido.mp4' }
      const content = { [asDocument ? 'documentMessage' : 'videoMessage']: media }
      const message = { message: { ephemeralMessage: { message: content } } }
      const parsed = parseInboundContent(message.message)
      assert.equal(parsed.kind, 'video')
      assert.equal(parsed.seconds, 3)
      assert.equal(parsed.text, caption || null)
      const bytes = Buffer.from([0, 0, 0, 24, 102, 116, 121, 112, 109, 112, 52, 50])
      let downloads = 0
      const buffer = await downloadInboundMedia(message, parsed, async (source, type) => {
        assert.equal(source, message)
        assert.equal(type, 'buffer')
        downloads += 1
        return bytes
      })
      const store = new IntakeStore(root)
      await store.initialize()
      const input = { project: 'example', receivedAt: new Date('2026-10-05T12:00:00Z'),
        manifest: { message_id: 'video-1', kind: parsed.kind, text: parsed.text,
          mime_type: parsed.mimeType, video_seconds: parsed.seconds, original_filename: parsed.fileName },
        mediaBuffer: buffer }
      const result = await store.persist(input)
      const saved = JSON.parse(await readFile(path.join(result.path, 'message.json')))
      assert.equal(saved.media_file, 'video-original.mp4')
      assert.equal(saved.mime_type, 'video/mp4')
      assert.equal(saved.video_seconds, 3)
      assert.equal(saved.text, caption || null)
      assert.equal(saved.media_bytes, bytes.length)
      assert.deepEqual(await readFile(path.join(result.path, saved.media_file)), bytes)
      assert.equal(await readFile(path.join(result.path, 'READY'), 'utf8'), '')
      assert.equal(await store.existsInAnyProject('video-1', input.receivedAt), true)
      assert.equal((await store.persist({ ...input, mediaBuffer: Buffer.from('changed') })).duplicate, true)
      assert.deepEqual(await readFile(path.join(result.path, saved.media_file)), bytes)
      assert.equal(downloads, 1)
    })
  }
}

test('video formats and captionless default remain video attachments', () => {
  assert.equal(parseInboundContent({ videoMessage: {} }).mimeType, 'video/mp4')
  assert.equal(parseInboundContent({ ptvMessage: { seconds: 5 } }).kind, 'video')
  assert.equal(parseInboundContent({ ptvMessage: { seconds: 5 } }).seconds, 5)
  for (const [extension, mime] of Object.entries({mp4: 'video/mp4', mov: 'video/quicktime',
    m4v: 'video/x-m4v', webm: 'video/webm', mkv: 'video/x-matroska', avi: 'video/x-msvideo',
    '3gp': 'video/3gpp', '3g2': 'video/3gpp2'})) {
    const parsed = parseInboundContent({ documentWithCaptionMessage: { message: {
      documentMessage: { fileName: `VIDEO.${extension.toUpperCase()}`, mimetype: 'application/octet-stream' },
    } } })
    assert.equal(parsed.kind, 'video')
    assert.equal(parsed.mimeType, mime)
    assert.equal(extensionForMime(mime), `.${extension}`)
  }
  assert.equal(parseInboundContent({ documentMessage: { fileName: 'other.exe' } }), null)
  assert.equal(parseInboundContent({ documentMessage: { fileName: 'other.constructor' } }), null)
})

test('failed or empty downloads fail before persistence', async () => {
  const parsed = parseInboundContent({ videoMessage: {} })
  await assert.rejects(downloadInboundMedia({}, parsed, async () => { throw new Error('offline') }), /offline/)
  await assert.rejects(downloadInboundMedia({}, parsed, async () => Buffer.alloc(0)), /no bytes/)
  assert.equal(await downloadInboundMedia({}, { media: null }, () => { throw new Error('called') }), null)
})

import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'
import { parseInboundContent, downloadInboundMedia } from '../src/message-content.mjs'
import { IntakeStore } from '../src/store.mjs'

for (const name of ['certificado.crt', 'facturacion.csr', 'datos.xlsx', 'archivo.bin', 'READY', '../../message.json', 'C:\\tmp\\certificado.crt']) {
  test(`captures document safely and byte-for-byte: ${name}`, async t => {
    const dir = await mkdtemp(path.join(os.tmpdir(), 'wa-doc-'))
    t.after(() => rm(dir, { recursive: true, force: true }))
    const store = new IntakeStore(dir)
    await store.initialize()
    const input = { documentWithCaptionMessage: { message: { documentMessage: { fileName: name, mimetype: 'application/octet-stream' } } } }
    const parsed = parseInboundContent(input)
    assert.equal(parsed.kind, 'document')
    assert.equal(parsed.fileName, name)
    assert.equal(parsed.text, null)
    const bytes = Buffer.from([0, 255, 13, 10, 128, 42])
    const mediaBuffer = await downloadInboundMedia(input, parsed, async () => bytes)
    const options = { project: 'example', mediaBuffer, receivedAt: new Date('2026-10-26T12:00:00Z'), ready: false,
      manifest: { message_id: 'one', kind: parsed.kind, original_filename: parsed.fileName, mime_type: parsed.mimeType } }
    const saved = await store.persist(options)
    const manifest = JSON.parse(await readFile(path.join(saved.path, 'message.json')))
    assert.equal(manifest.original_filename, name)
    assert.equal(manifest.mime_type, 'application/octet-stream')
    assert.equal(path.basename(manifest.media_file), manifest.media_file)
    assert.match(manifest.media_file, /^document-original-/)
    assert.deepEqual(await readFile(path.join(saved.path, manifest.media_file)), bytes)
    // Before READY (interactive selection), replay must not replace the original.
    assert.equal((await store.persist({ ...options, mediaBuffer: Buffer.from('changed') })).duplicate, true)
    assert.deepEqual(await readFile(path.join(saved.path, manifest.media_file)), bytes)
  })
}

test('generic document MIME fallback, caption, and failed download', async () => {
  const parsed = parseInboundContent({ documentMessage: { fileName: 'request.csr', caption: 'Guardar este archivo' } })
  assert.equal(parsed.mimeType, 'application/octet-stream')
  assert.equal(parsed.text, 'Guardar este archivo')
  await assert.rejects(downloadInboundMedia({}, parsed, async () => Buffer.alloc(0)), /no bytes/)
  await assert.rejects(downloadInboundMedia({}, parsed, async () => { throw new Error('download failed') }), /download failed/)
})

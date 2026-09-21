import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import { IntakeStore, extensionForMime } from '../src/store.mjs'

test('persists an audio intake atomically and deduplicates it', async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-ingest-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const store = new IntakeStore(root)
  await store.initialize()
  const receivedAt = new Date('2026-09-18T20:00:00.000Z')
  const manifest = {
    message_id: 'ABC/123',
    mime_type: 'audio/ogg; codecs=opus',
    text: null,
  }

  const first = await store.persist({
    manifest,
    mediaBuffer: Buffer.from('audio'),
    project: 'moldegom',
    receivedAt,
  })
  assert.equal(first.duplicate, false)
  assert.equal(await readFile(path.join(first.path, 'audio-original.ogg'), 'utf8'), 'audio')
  const saved = JSON.parse(await readFile(path.join(first.path, 'message.json'), 'utf8'))
  assert.equal(saved.media_file, 'audio-original.ogg')
  assert.equal(saved.media_bytes, 5)

  const second = await store.persist({
    manifest,
    mediaBuffer: Buffer.from('different'),
    project: 'moldegom',
    receivedAt,
  })
  assert.equal(second.duplicate, true)
})

test('maps common audio mime types to stable extensions', () => {
  assert.equal(extensionForMime('audio/ogg; codecs=opus'), '.ogg')
  assert.equal(extensionForMime('audio/mpeg'), '.mp3')
  assert.equal(extensionForMime('unknown/type'), '.bin')
})

test('promotes records from a pending inbox when the group becomes matched', async (t) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-ingest-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const store = new IntakeStore(root)
  await store.initialize()
  const receivedAt = new Date('2026-09-18T20:00:00.000Z')
  const manifest = { message_id: 'MOVE-1', mime_type: null, text: 'hola' }
  await store.persist({ manifest, project: 'pending-cliente-123', receivedAt })

  assert.equal(await store.promotePendingProject('pending-cliente-123', 'cliente'), 1)
  assert.equal(await store.exists('cliente', 'MOVE-1', receivedAt), true)
})

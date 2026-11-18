import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, rm, stat } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { createHash, createHmac, createCipheriv, randomBytes } from 'node:crypto'
import { proto } from '@whiskeysockets/baileys'
import { PollEcho } from '../src/poll-echo.mjs'

const recipient = '5491100000000@s.whatsapp.net'
const creator = '5491199999999@s.whatsapp.net'
function encrypted(secret, option, voter = recipient) {
  const first = createHmac('sha256', Buffer.alloc(32)).update(secret).digest()
  const key = createHmac('sha256', first).update(Buffer.concat([
    Buffer.from('poll-1'), Buffer.from(creator), Buffer.from(voter), Buffer.from('Poll Vote'), Buffer.from([1]),
  ])).digest()
  const encIv = randomBytes(12)
  const cipher = createCipheriv('aes-256-gcm', key, encIv)
  cipher.setAAD(Buffer.from(`poll-1\0${voter}`))
  const selectedOptions = option ? [createHash('sha256').update(option).digest()] : []
  const body = proto.Message.PollVoteMessage.encode({ selectedOptions }).finish()
  return { encIv, encPayload: Buffer.concat([cipher.update(body), cipher.final(), cipher.getAuthTag()]) }
}

test('real encrypted choices, persistence, isolation, deduplication and uncertain delivery', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'poll-echo-'))
  try {
    const file = path.join(dir, 'state.json')
    const echo = new PollEcho({ file, recipient })
    const sent = []
    const secret = randomBytes(32)
    const socket = { user: { id: creator }, sendMessage: async (jid, content) => {
      sent.push({ jid, content })
      return { key: { id: content.poll ? 'poll-1' : `reply-${sent.length}` }, message: { messageContextInfo: { messageSecret: secret } } }
    } }
    await echo.start(socket)
    assert.equal(sent.length, 0)
    await echo.save({ status: 'requested', source_ref: 'test:explicit' })
    await echo.start(socket)
    await echo.start(socket)
    assert.equal(sent.length, 1)
    assert.equal((await stat(file)).mode & 0o777, 0o600)
    let timestamp = 100
    function message(option, id, remote = recipient, poll = 'poll-1') {
      return { key: { id, remoteJid: remote, fromMe: false }, message: { pollUpdateMessage: {
        pollCreationMessageKey: { id: poll, fromMe: true }, vote: encrypted(secret, option), senderTimestampMs: timestamp++,
      } } }
    }
    assert.equal(await echo.handle(socket, { key: {}, message: { conversation: 'CLI' } }), false)
    await echo.handle(socket, message('WhatsApp', 'wrong-person', '999@s.whatsapp.net'))
    await echo.handle(socket, message('WhatsApp', 'wrong-poll', recipient, 'other'))
    assert.equal(sent.length, 1)
    const first = message('WhatsApp', 'vote-1')
    await Promise.all([echo.handle(socket, first), echo.handle(socket, first)])
    assert.equal(sent.length, 2)
    assert.equal(sent[1].content.text, 'Elegiste: WhatsApp.')
    const restarted = new PollEcho({ file, recipient })
    await restarted.handle(socket, first)
    await restarted.handle(socket, message('Bridge', 'vote-2'))
    assert.equal(sent.length, 3)
    assert.equal(sent[2].content.text, 'Elegiste: Bridge.')
    await restarted.handle(socket, message(null, 'withdrawal'))
    await restarted.handle(socket, message('unknown', 'unknown'))
    assert.equal(sent.length, 3)
    const invalid = message('Bridge', 'corrupt')
    invalid.message.pollUpdateMessage.vote.encPayload[0] ^= 1
    await restarted.handle(socket, invalid)
    assert.equal(sent.length, 3)
    const uncertain = message('WhatsApp', 'uncertain')
    let attempts = 0
    const broken = { sendMessage: async () => { attempts++; throw new Error('network') } }
    await assert.rejects(restarted.handle(broken, uncertain))
    await restarted.handle(broken, uncertain)
    assert.equal(attempts, 1)
  } finally { await rm(dir, { recursive: true, force: true }) }
})

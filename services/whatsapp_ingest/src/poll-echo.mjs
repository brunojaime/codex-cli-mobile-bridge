import { readFile, writeFile, rename } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import { decryptPollVote, jidNormalizedUser } from '@whiskeysockets/baileys'

// An explicit local experiment, never a general autoresponder.
export class PollEcho {
  constructor({ file, recipient }) {
    this.file = file
    this.recipient = recipient
    this.queue = Promise.resolve()
  }
  async read() {
    try { return JSON.parse(await readFile(this.file, 'utf8')) }
    catch (error) { if (error.code === 'ENOENT') return null; throw error }
  }
  async save(state) {
    await writeFile(`${this.file}.tmp`, JSON.stringify(state), { mode: 0o600 })
    await rename(`${this.file}.tmp`, this.file)
  }
  serial(action) {
    const result = this.queue.then(action)
    this.queue = result.catch(() => {})
    return result
  }
  start(socket) {
    return this.serial(async () => {
      const state = await this.read()
      if (!state || state.status !== 'requested' || !state.source_ref) return
      state.status = 'sending_poll'
      await this.save(state) // An uncertain send is not retried automatically.
      const options = ['WhatsApp', 'Bridge']
      const sent = await socket.sendMessage(this.recipient, {
        poll: { name: 'Elegí una opción y te digo cuál elegiste', values: options, selectableCount: 1 },
      })
      Object.assign(state, {
        status: 'awaiting_vote', poll_id: sent.key.id, options,
        secret: Buffer.from(sent.message.messageContextInfo.messageSecret).toString('base64'),
        creators: [socket.user.id, socket.user.lid].filter(Boolean).map(jidNormalizedUser),
        sent_at: new Date().toISOString(), votes: {},
      })
      await this.save(state)
    })
  }
  handle(socket, message) {
    return this.serial(async () => {
      const update = message.message?.pollUpdateMessage
      if (!update) return false
      const state = await this.read()
      if (!state?.poll_id || update.pollCreationMessageKey?.id !== state.poll_id) return false
      if (message.key.fromMe || update.pollCreationMessageKey.fromMe !== true) return true
      const voters = [message.key.remoteJid, message.key.remoteJidAlt].filter(Boolean).map(jidNormalizedUser)
      if (!voters.includes(this.recipient) && message.key.remoteJid?.endsWith('@lid')) {
        const pn = await socket.signalRepository?.lidMapping?.getPNForLID(message.key.remoteJid)
        if (pn) voters.push(jidNormalizedUser(pn))
      }
      if (!voters.includes(this.recipient)) return true
      if (!['awaiting_vote', 'active'].includes(state.status)) return true
      if (!message.key.id || state.votes[message.key.id]) return true
      let vote
      for (const creator of state.creators) {
        for (const voter of voters) {
          try {
            vote = decryptPollVote(update.vote, { pollCreatorJid: creator, voterJid: voter,
              pollMsgId: state.poll_id, pollEncKey: Buffer.from(state.secret, 'base64') })
            break
          } catch { /* PN and LID addressing can differ; try authenticated alternatives. */ }
        }
        if (vote) break
      }
      if (!vote) { state.last_error = 'vote_decryption_failed'; await this.save(state); return true }
      const selected = vote.selectedOptions || []
      const option = state.options.find(value => selected.length === 1 &&
        createHash('sha256').update(value).digest().equals(Buffer.from(selected[0])))
      if (!option) return true // Deselection and unknown values never invent a choice.
      const stamp = Number(update.senderTimestampMs || 0)
      if (state.last_timestamp && stamp <= state.last_timestamp) return true
      state.votes[message.key.id] = { status: 'sending', option }
      state.last_timestamp = stamp
      await this.save(state)
      const reply = await socket.sendMessage(this.recipient, { text: `Elegiste: ${option}.` })
      state.votes[message.key.id] = { status: 'submitted', option, reply_id: reply.key.id,
        at: new Date().toISOString() }
      state.status = 'active'
      delete state.last_error
      await this.save(state)
      return true
    })
  }
}

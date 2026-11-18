import { mkdir, readFile, writeFile, rename, readdir } from 'node:fs/promises'
import path from 'node:path'
import { createHash, randomUUID } from 'node:crypto'
import { decryptPollVote, jidNormalizedUser, normalizeMessageContent } from '@whiskeysockets/baileys'

const PROJECTS_PER_PAGE = 5
const RECIPIENT = '5491132788446@s.whatsapp.net'
async function read(file) {
  try { return JSON.parse(await readFile(file, 'utf8')) }
  catch (error) { if (error.code === 'ENOENT') return null; throw error }
}
async function save(file, value) {
  await mkdir(path.dirname(file), { recursive: true, mode: 0o700 })
  await writeFile(`${file}.tmp`, JSON.stringify(value), { mode: 0o600 })
  await rename(`${file}.tmp`, file)
}
export class InteractiveIntake {
  constructor({ dataDir, recipient = RECIPIENT, settleMs = 6000 }) {
    this.dataDir = dataDir
    this.root = path.join(dataDir, 'interactive')
    this.file = path.join(this.root, 'dialog.json')
    this.recipient = recipient
    this.settleMs = settleMs
    this.queue = Promise.resolve()
  }
  serial(action) {
    const result = this.queue.then(action)
    this.queue = result.catch(() => {})
    return result
  }
  async enabled() { return Boolean((await read(path.join(this.root, 'config.json')))?.enabled) }
  async authorized(socket, message) {
    if (message.key?.fromMe) return false
    const ids = [message.key?.remoteJid, message.key?.remoteJidAlt].filter(Boolean).map(jidNormalizedUser)
    if (!ids.includes(this.recipient) && message.key?.remoteJid?.endsWith('@lid')) {
      const pn = await socket.signalRepository?.lidMapping?.getPNForLID(message.key.remoteJid)
      if (pn) ids.push(jidNormalizedUser(pn))
    }
    return ids.includes(this.recipient)
  }
  async control(socket, message, text) {
    if (!await this.enabled() || !await this.authorized(socket, message)) return false
    const command = String(text || '').trim().toLowerCase()
    if (!['nuevo', 'menú', 'menu', 'cambiar destino', 'cancelar', 'estado'].includes(command)) return false
    return this.serial(async () => {
      const state = await read(this.file) || {}
      if (command === 'estado') {
        const request = state.id ? await read(path.join(this.root, 'requests', `${state.id}.json`)) : null
        await socket.sendMessage(this.recipient, { text: `Estado: ${request?.status || state.phase || 'sin pedido'}. Proyecto: ${state.project || 'sin elegir'}. Canal: ${state.channel || 'sin elegir'}.` })
        return true
      }
      // Submitted work continues; this only resets the destination for future requests.
      if (state.phase !== 'submitted') {
        state.phase = 'cancelled'
      }
      state.reset_next = true
      state.session_id = null
      await this.saveDialog(state)
      await socket.sendMessage(this.recipient, { text: command === 'cancelar'
        ? 'Cancelé la selección pendiente. Los trabajos ya enviados siguen su curso.'
        : 'Mandame el nuevo pedido y te muestro las opciones de destino.' })
      return true
    })
  }
  async dialogs() {
    const dir = path.join(this.root, 'dialogs')
    let names = []
    try { names = await readdir(dir) } catch (e) { if (e.code !== 'ENOENT') throw e }
    return Promise.all(names.filter(n => n.endsWith('.json')).map(n => read(path.join(dir, n))))
  }
  async saveDialog(state) {
    if (!state.id) { await save(this.file, state); return }
    await save(path.join(this.root, 'dialogs', `${state.id}.json`), state)
    const current = await read(this.file)
    if (current?.id === state.id) await save(this.file, state)
  }
  async quotedRequest(socket, message) {
    const content = normalizeMessageContent(message.message)
    const context = Object.values(content || {}).find(v => v?.contextInfo?.stanzaId)?.contextInfo
    if (!context?.stanzaId) return null
    const ownIds = [socket.user?.id, socket.user?.lid].filter(Boolean).map(jidNormalizedUser)
    if (!ownIds.includes(jidNormalizedUser(context.participant || ''))) return null
    // Only IDs actually returned by sending a final response may select a session.
    const dir = path.join(this.root, 'requests')
    let names = []
    try { names = await readdir(dir) } catch (e) { if (e.code !== 'ENOENT') throw e }
    for (const name of names.filter(n => n.endsWith('.json'))) {
      const request = await read(path.join(dir, name))
      if (request?.channel === 'whatsapp' && request.session_id &&
          request.delivery_ids?.includes(context.stanzaId)) return request
    }
    return null
  }
  async capture(socket, message, recordPath, text) {
    if (!await this.authorized(socket, message)) throw new Error('Unauthorized interactive sender')
    return this.serial(async () => {
      let state = await read(this.file)
      const id = message.key.id
      if (state?.seen?.includes(id)) return
      const dialogs = await this.dialogs()
      if (dialogs.some(d => d.seen?.includes(id))) return
      const previous = await this.quotedRequest(socket, message)
      const replyTo = previous?.id || null
      const pending = state && ['collecting', 'awaiting_vote'].includes(state.phase) && !state.reset_next
      // Multipart messages may join a pending selection only with the same reply target.
      if (!pending || (state.reply_to_request || null) !== replyTo) {
        if (state?.id) await this.saveDialog(state)
        state = { id: randomUUID(), phase: 'collecting', records: [], seen: [], polls: [],
          created_at: Date.now(), project: previous?.project || null,
          cli: previous?.cli || false, channel: previous ? 'whatsapp' : null,
          session_id: previous?.session_id || null, reply_to_request: replyTo }
        await save(this.file, state)
      }
      state.records.push(path.relative(this.dataDir, recordPath))
      state.seen.push(id)
      state.last_received = Date.now()
      const project = String(text || '').match(/^\s*proyecto\s*:\s*([^\n]+)$/im)?.[1]?.trim()
      const cli = /^\s*cli\s*$/im.test(String(text || ''))
      const channel = String(text || '').match(/^\s*(?:canal|respuesta)\s*:\s*(whatsapp|bridge)\s*$/im)?.[1]?.toLowerCase()
      if (project) {
        if (state.project && state.project !== project) state.conflict = true
        state.project = project
      }
      if (cli) {
        if (state.project && state.project !== 'codex-cli-mobile-bridge') state.conflict = true
        state.cli = true; state.project = 'codex-cli-mobile-bridge'
      }
      if (channel) {
        if (state.channel && state.channel !== channel) state.conflict = true
        state.channel = channel
      }
      await this.saveDialog(state)
    })
  }
  async poll(socket, state, kind, options, title) {
    const pending = { kind, options, status: 'sending', at: Date.now() }
    state.polls.push(pending)
    state.phase = 'awaiting_vote'
    await this.saveDialog(state)
    const sent = await socket.sendMessage(this.recipient, { poll: {
      name: title, values: options.map(o => o.label), selectableCount: 1,
    } })
    Object.assign(pending, { id: sent.key.id, status: 'open',
      secret: Buffer.from(sent.message.messageContextInfo.messageSecret).toString('base64'),
      creators: [socket.user.id, socket.user.lid].filter(Boolean).map(jidNormalizedUser) })
    await this.saveDialog(state)
  }
  async advance(socket, state) {
    if (state.conflict) {
      state.phase = 'cancelled'; await this.saveDialog(state)
      await socket.sendMessage(this.recipient, { text: 'Encontré destinos distintos en el pedido. Escribí «nuevo» y elegí uno.' })
      return
    }
    if (state.depends_on) {
      const previous = await read(path.join(this.root, 'requests', `${state.depends_on}.json`))
      if (previous?.status !== 'delivered') return
      state.session_id = previous.session_id
      state.depends_on = null
    }
    const catalog = await read(path.join(this.root, 'catalog.json'))
    if (!catalog?.projects?.length || Date.now() - catalog.updated_at * 1000 > 120000) {
      if (!state.catalog_notice) {
        state.catalog_notice = true; await this.saveDialog(state)
        await socket.sendMessage(this.recipient, { text: 'No pude actualizar la lista de proyectos. Tu pedido está guardado y voy a reintentar.' })
      }
      return
    }
    if (state.project && !catalog.projects.some(p => p.slug === state.project)) {
      // Resolve exact aliases only through the worker; let the user select a canonical workspace.
      const matches = catalog.projects.filter(p => (p.aliases || []).some(a => a.toLowerCase() === state.project.toLowerCase()))
      state.project = matches.length === 1 ? matches[0].slug : null
    }
    if (!state.project) {
      state.catalog ||= catalog.projects
      const page = state.page || 0
      const options = state.catalog.slice(page * PROJECTS_PER_PAGE, (page + 1) * PROJECTS_PER_PAGE).map(p => ({ label: p.slug, project: p.slug }))
      options.unshift({ label: 'CLI general', project: 'codex-cli-mobile-bridge', cli: true })
      if (page > 0) options.push({ label: '← Anteriores', page: page - 1 })
      if ((page + 1) * PROJECTS_PER_PAGE < state.catalog.length) options.push({ label: 'Más proyectos →', page: page + 1 })
      options.push({ label: 'Cancelar', cancel: true })
      await this.poll(socket, state, 'project', options, '¿En qué proyecto? · Más recientes primero')
    } else if (!state.channel) {
      await this.poll(socket, state, 'channel', [
        { label: 'WhatsApp · Charlar', channel: 'whatsapp' },
        { label: 'Bridge · Ejecutar', channel: 'bridge' },
        { label: 'Backlog · Ejecutar después', channel: 'backlog' },
        { label: 'Cancelar', cancel: true },
      ], '¿Cómo querés atender el pedido?')
    } else {
      const file = path.join(this.root, 'requests', `${state.id}.json`)
      if (!await read(file)) await save(file, { id: state.id, status: 'queued',
        records: state.records, project: state.project, cli: state.cli,
        channel: state.channel, session_id: state.session_id, reply_to_request: state.reply_to_request || null, created_at: Date.now() })
      state.phase = 'submitted'
      await this.saveDialog(state)
      await socket.sendMessage(this.recipient, { text: state.channel === 'backlog'
        ? `Recibí el pedido para el backlog de ${state.project}. Te confirmo cuando quede guardado; no se abre otro chat ahora.`
        : `Pedido enviado a ${state.cli ? 'CLI general' : state.project}. ${state.channel === 'whatsapp' ? 'Te respondo por WhatsApp.' : 'Lo seguimos en Codex Bridge.'}` })
    }
  }
  async handleVote(socket, message) {
    if (!message.message?.pollUpdateMessage || !await this.enabled()) return false
    return this.serial(async () => {
      let state = await read(this.file)
      const update = message.message.pollUpdateMessage
      const pollId = update.pollCreationMessageKey?.id
      if (!state?.polls?.some(p => p.id === pollId)) {
        state = (await this.dialogs()).find(d => d.polls?.some(p => p.id === pollId))
      }
      const poll = state?.polls?.find(p => p.id === pollId)
      if (!poll) return false
      if (!await this.authorized(socket, message) || !update.pollCreationMessageKey.fromMe) return true
      if (poll.status !== 'open' || state.phase !== 'awaiting_vote') return true
      const voters = [message.key.remoteJid, message.key.remoteJidAlt, this.recipient].filter(Boolean).map(jidNormalizedUser)
      let vote
      for (const creator of poll.creators) {
        for (const voter of voters) {
          try { vote = decryptPollVote(update.vote, { pollCreatorJid: creator, voterJid: voter,
            pollMsgId: poll.id, pollEncKey: Buffer.from(poll.secret, 'base64') }); break } catch {}
        }
        if (vote) break
      }
      const selected = vote?.selectedOptions || []
      const option = poll.options.find(o => selected.length === 1 &&
        createHash('sha256').update(o.label).digest().equals(Buffer.from(selected[0])))
      if (!option) return true
      poll.status = 'consumed'; poll.vote_id = message.key.id
      if (option.cancel) state.phase = 'cancelled'
      if (option.project) { state.project = option.project; state.cli = Boolean(option.cli) }
      if (option.channel) state.channel = option.channel
      if (option.page !== undefined) state.page = option.page
      await this.saveDialog(state)
      if (!option.cancel) await this.advance(socket, state)
      else await socket.sendMessage(this.recipient, { text: 'Selección cancelada. Tu material quedó conservado.' })
      return true
    })
  }
  async tick(socket) {
    if (!socket || !await this.enabled()) return
    return this.serial(async () => {
      let state = await read(this.file)
      const pendingDialogs = await this.dialogs()
      if (state?.id && !pendingDialogs.some(d => d.id === state.id)) pendingDialogs.push(state)
      for (const dialog of pendingDialogs) {
        if ((dialog?.phase === 'collecting' || (dialog?.phase === 'awaiting_vote' && dialog.polls?.every(p => p.status === 'consumed'))) && Date.now() - dialog.last_received >= this.settleMs) {
          await this.advance(socket, dialog)
        }
        if (dialog?.phase === 'awaiting_vote' && Date.now() - dialog.last_received > 15 * 60000) {
          dialog.phase = 'expired'; await this.saveDialog(dialog)
          await socket.sendMessage(this.recipient, { text: 'La selección venció. Escribí «nuevo» para empezar otra; conservé el material.' })
        }
      }
      // Deliver completed requests even if a new dialog has started.
      const dir = path.join(this.root, 'requests')
      let names = []; try { names = await readdir(dir) } catch (e) { if (e.code !== 'ENOENT') throw e }
      for (const name of names.filter(n => n.endsWith('.json'))) {
        const file = path.join(dir, name)
        const request = await read(file)
        if (request?.status !== 'finished') continue
        request.status = 'delivering'; await save(file, request)
        if (request.channel === 'whatsapp' || request.channel === 'backlog') {
          const chunks = request.reply.match(/[\s\S]{1,3500}/g) || ['Sin respuesta de texto.']
          request.delivery_ids = []
          for (const text of chunks) {
            const sent = await socket.sendMessage(this.recipient, { text })
            request.delivery_ids.push(sent.key.id)
            await save(file, request)
          }
        }
        request.status = 'delivered'; request.delivered_at = Date.now()
        await save(file, request)
        state = await read(this.file)
        if (state?.id === request.id) {
          state.phase = 'done'; state.session_id = request.session_id
          await this.saveDialog(state)
        }
      }
    })
  }
}

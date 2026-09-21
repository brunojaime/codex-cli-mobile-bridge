import { mkdir, readFile, readdir, rename, writeFile } from 'node:fs/promises'
import path from 'node:path'

import { normalizeIdentity, participantJids } from './project-reconciler.mjs'

const STATE_VERSION = 1
const MAX_PROCESSED_MESSAGES = 200

export class AdminGroupManager {
  constructor({ dataDir, logger = null, stateFile, subject }) {
    this.dataDir = path.resolve(dataDir)
    this.logger = logger
    this.stateFile = path.resolve(stateFile)
    this.subject = String(subject || 'Nienfos · Alta de grupos').trim()
    this.state = null
  }

  async ensureGroup(socket, groups) {
    const state = await this.#loadOrBootstrapState()
    const existing = state.group_id
      ? groups.find((group) => group.id === state.group_id)
      : groups.find((group) => normalizeIdentity(group.subject) === normalizeIdentity(state.subject))
    const group = existing || await socket.groupCreate(
      state.subject,
      [state.people.bruno.phone_jid],
    )
    if (!existing) {
      await socket.groupUpdateDescription(
        group.id,
        'Canal privado para altas de grupos de proyectos. Sólo Bruno o Mariano pueden solicitar operaciones. No se envían respuestas automáticas.',
      )
      groups.push(group)
    }
    if (state.group_id !== group.id) {
      state.group_id = group.id
      state.created_at ||= new Date().toISOString()
      await this.#saveState()
    }
    return group
  }

  isAdminGroup(groupId) {
    return Boolean(this.state?.group_id && this.state.group_id === groupId)
  }

  isAdminMetadata(group) {
    if (!group) return false
    return this.isAdminGroup(group.id)
      || normalizeIdentity(group.subject) === normalizeIdentity(this.subject)
  }

  summary(group) {
    return {
      active: true,
      candidates: [],
      group_id: group.id,
      id: group.id,
      inbox_project: 'whatsapp-group-admin',
      project: null,
      source: 'admin_control',
      status: 'administrative',
      subject: group.subject || this.subject,
    }
  }

  async handleMessage({ message, text, socket, projects, createProjectGroup }) {
    const state = this.state
    if (!state || !this.isAdminGroup(message?.key?.remoteJid)) {
      return { handled: false, status: 'not_admin_group' }
    }
    const messageId = String(message?.key?.id || '').trim()
    if (messageId && state.processed_message_ids.includes(messageId)) {
      return { handled: true, status: 'duplicate' }
    }
    const senderJids = senderIdentities(message)
    const role = authorizedRole(state, senderJids)
    if (!role) {
      this.logger?.warn?.(
        { groupId: state.group_id, messageId },
        'Ignoring unauthorized WhatsApp group administration command',
      )
      return { handled: true, status: 'unauthorized' }
    }

    const command = parseAdminCommand(text)
    if (!command) return { handled: true, status: 'ignored' }

    if (command.type === 'register_mariano') {
      if (role !== 'bruno') return { handled: true, status: 'unauthorized' }
      const phoneJid = participantJids([command.phone])[0]
      await socket.groupParticipantsUpdate(state.group_id, [phoneJid], 'add')
      state.people.mariano = {
        jids: [phoneJid],
        phone_jid: phoneJid,
        registered_at: new Date().toISOString(),
      }
      await this.#markProcessed(messageId)
      this.logger?.info?.(
        { groupId: state.group_id, role: 'mariano' },
        'Registered core WhatsApp group administrator',
      )
      return { handled: true, status: 'mariano_registered' }
    }

    if (!state.people.mariano?.phone_jid) {
      return { handled: true, status: 'mariano_not_registered' }
    }
    const resolution = resolveProjectHint(command.projectHint, projects)
    if (!resolution) {
      this.logger?.warn?.(
        { groupId: state.group_id, messageId, projectHint: command.projectHint },
        'Could not confidently resolve project for WhatsApp group creation',
      )
      return { handled: true, status: 'project_unresolved' }
    }
    const coreJids = [
      state.people.bruno.phone_jid,
      state.people.mariano.phone_jid,
    ]
    const clientJids = participantJids(command.phones)
      .filter((jid) => !coreJids.includes(jid))
    const participants = [...new Set([...coreJids, ...clientJids])]
    const created = await createProjectGroup({
      participants,
      project: resolution.project,
      subject: command.subject,
    })
    await this.#markProcessed(messageId)
    return {
      handled: true,
      status: 'group_created',
      groupId: created.id,
      project: resolution.project.slug,
    }
  }

  async #loadOrBootstrapState() {
    if (this.state) return this.state
    try {
      const value = JSON.parse(await readFile(this.stateFile, 'utf8'))
      validateState(value)
      this.state = value
      return value
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error
    }

    const bruno = await discoverPersonIdentity(this.dataDir, 'bruno')
    if (!bruno?.phone_jid) {
      throw new Error('Could not discover Bruno WhatsApp identity from captured messages.')
    }
    this.state = {
      version: STATE_VERSION,
      subject: this.subject,
      group_id: null,
      created_at: null,
      people: {
        bruno,
        mariano: null,
      },
      processed_message_ids: [],
    }
    await this.#saveState()
    return this.state
  }

  async #markProcessed(messageId) {
    if (messageId) {
      this.state.processed_message_ids.push(messageId)
      this.state.processed_message_ids = [
        ...new Set(this.state.processed_message_ids),
      ].slice(-MAX_PROCESSED_MESSAGES)
    }
    await this.#saveState()
  }

  async #saveState() {
    await mkdir(path.dirname(this.stateFile), { recursive: true, mode: 0o700 })
    const temporary = `${this.stateFile}.${process.pid}.${Date.now()}.tmp`
    await writeFile(temporary, `${JSON.stringify(this.state, null, 2)}\n`, {
      encoding: 'utf8',
      mode: 0o600,
    })
    await rename(temporary, this.stateFile)
  }
}

export function parseAdminCommand(value) {
  const text = String(value || '').trim()
  if (!text) return null
  const normalized = normalizeIdentity(text)
  const phones = extractPhoneNumbers(text)
  if (normalized.includes('mariano') && phones.length && !isCreateGroupCommand(normalized)) {
    return { type: 'register_mariano', phone: phones[0] }
  }
  if (!isCreateGroupCommand(normalized)) return null

  const fields = parseLabeledFields(text)
  const subject = cleanSubject(
    fields.group
      || quotedGroupSubject(text)
      || inlineGroupSubject(text),
  )
  if (!subject) return null
  const projectHint = String(fields.project || subject).trim()
  return {
    type: 'create_group',
    subject,
    projectHint,
    phones,
  }
}

export function resolveProjectHint(value, projects) {
  const hint = normalizeIdentity(value)
  const compactHint = hint.replace(/\s+/g, '')
  if (!hint || !compactHint) return null
  const matches = []
  for (const project of projects || []) {
    let score = 0
    for (const identifierValue of project.identifiers || []) {
      const identifier = normalizeIdentity(identifierValue)
      const compact = identifier.replace(/\s+/g, '')
      if (!identifier) continue
      if (identifier === hint) score = Math.max(score, 1)
      else if (compact === compactHint) score = Math.max(score, 0.99)
      else if (
        compactHint.length >= 4
        && (compact.startsWith(compactHint) || compactHint.startsWith(compact))
      ) score = Math.max(score, 0.9)
    }
    if (score >= 0.9) matches.push({ project, score })
  }
  matches.sort((left, right) => right.score - left.score)
  if (!matches.length) return null
  if (matches.length > 1 && matches[0].score === matches[1].score) return null
  return matches[0]
}

function isCreateGroupCommand(normalized) {
  return normalized.includes('crear') && normalized.includes('grupo')
}

function parseLabeledFields(text) {
  const result = {}
  for (const segment of text.split(/[|\n;]/)) {
    const match = segment.match(/^\s*(?:crear\s+)?(grupo|nombre|proyecto|clientes?|usuarios?|participantes?)\s*:\s*(.+?)\s*$/i)
    if (!match) continue
    const key = normalizeIdentity(match[1])
    if (key === 'grupo' || key === 'nombre') result.group = match[2]
    if (key === 'proyecto') result.project = match[2]
  }
  return result
}

function quotedGroupSubject(text) {
  return text.match(/grupo(?:\s+que\s+se\s+llame|\s+llamado)?\s*[«“"']([^»”"']+)[»”"']/i)?.[1]
}

function inlineGroupSubject(text) {
  return text.match(/(?:crear|crea(?:te)?)\s+(?:un\s+)?grupo(?:\s+que\s+se\s+llame|\s+llamado)?\s+(.+?)(?=\s+(?:para|del|de\s+proyecto|proyecto|con|agrega|agregar|inclui|clientes?|usuarios?|participantes?)\b|[,;|\n]|$)/i)?.[1]
}

function cleanSubject(value) {
  const subject = String(value || '').trim().replace(/^[«“"']|[»”"']$/g, '').trim()
  if (!subject || subject.length > 100) return null
  return subject
}

function extractPhoneNumbers(text) {
  const values = []
  for (const match of String(text || '').matchAll(/(?:\+?\d[\d\s().-]{6,}\d)/g)) {
    const digits = match[0].replace(/\D/g, '')
    if (digits.length >= 8 && digits.length <= 15) values.push(`+${digits}`)
  }
  return [...new Set(values)]
}

function senderIdentities(message) {
  return new Set([
    message?.key?.participant,
    message?.key?.participantAlt,
  ].filter(Boolean).map(normalizeJid))
}

function authorizedRole(state, senderJids) {
  for (const role of ['bruno', 'mariano']) {
    const person = state.people[role]
    if (!person) continue
    if (person.jids.some((jid) => senderJids.has(normalizeJid(jid)))) return role
  }
  return null
}

async function discoverPersonIdentity(dataDir, normalizedName) {
  const inbox = path.join(dataDir, 'inbox')
  const manifests = await findMessageManifests(inbox)
  const candidates = new Map()
  for (const filename of manifests) {
    try {
      const manifest = JSON.parse(await readFile(filename, 'utf8'))
      if (normalizeIdentity(manifest.push_name) !== normalizedName) continue
      const jids = [manifest.participant_id, manifest.participant_alt_id]
        .filter(Boolean)
        .map(normalizeJid)
      const phoneJid = jids.find((jid) => jid.endsWith('@s.whatsapp.net'))
      if (phoneJid) {
        const previous = candidates.get(phoneJid)
        candidates.set(phoneJid, {
          jids: [...new Set([...(previous?.jids || []), ...jids])],
          phone_jid: phoneJid,
          registered_at: new Date().toISOString(),
        })
      }
    } catch {
      // A malformed historical record must not block identity discovery.
    }
  }
  if (candidates.size > 1) {
    throw new Error(`Found multiple WhatsApp phone identities for ${normalizedName}.`)
  }
  return [...candidates.values()][0] || null
}

async function findMessageManifests(directory) {
  let entries
  try {
    entries = await readdir(directory, { withFileTypes: true })
  } catch (error) {
    if (error?.code === 'ENOENT') return []
    throw error
  }
  const result = []
  for (const entry of entries) {
    const filename = path.join(directory, entry.name)
    if (entry.isDirectory()) result.push(...await findMessageManifests(filename))
    else if (entry.name === 'message.json') result.push(filename)
  }
  return result
}

function normalizeJid(value) {
  return String(value || '').trim().toLowerCase()
}

function validateState(value) {
  if (value?.version !== STATE_VERSION || !value.people?.bruno?.phone_jid) {
    throw new Error('Invalid WhatsApp admin group state.')
  }
  value.processed_message_ids ||= []
}

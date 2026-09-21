import { mkdir } from 'node:fs/promises'
import path from 'node:path'
import process from 'node:process'
import makeWASocket, {
  DisconnectReason,
  downloadMediaMessage,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  useMultiFileAuthState,
} from '@whiskeysockets/baileys'
import pino from 'pino'
import QRCode from 'qrcode'

import { AdminGroupManager } from './admin-groups.mjs'
import { createAdminServer } from './admin-server.mjs'
import { CommunityManager } from './community-manager.mjs'
import { isDirectChat, parseDirectProjectDirective } from './direct-intake.mjs'
import { loadGroupMappings, loadSettings } from './config.mjs'
import { parseInboundContent, parseSharedContacts, timestampSeconds } from './message-content.mjs'
import { ProjectFactoryClient } from './project-factory-client.mjs'
import { normalizeIdentity, participantJids, ProjectReconciler } from './project-reconciler.mjs'
import { IntakeStore } from './store.mjs'

const settings = loadSettings()
const logger = pino({ level: settings.logLevel })
const whatsappLogger = logger.child({ component: 'baileys' })
whatsappLogger.level = process.env.WHATSAPP_PROTOCOL_LOG_LEVEL || 'warn'

await mkdir(settings.authDir, { recursive: true, mode: 0o700 })
const store = new IntakeStore(settings.dataDir)
await store.initialize()
const reconciler = new ProjectReconciler({
  logger,
  projectsRoot: settings.projectsRoot,
  registryFile: settings.registryFile,
})
const projectFactory = new ProjectFactoryClient({ baseUrl: settings.projectFactoryUrl })
const adminGroups = new AdminGroupManager({
  dataDir: settings.dataDir,
  logger,
  stateFile: settings.adminGroupStateFile,
  subject: settings.adminGroupSubject,
})
const communities = new CommunityManager({
  logger,
  stateFile: settings.communityStateFile,
  subject: settings.communitySubject,
})

const runtime = createRuntimeState()
createAdminServer({
  state: runtime,
  host: settings.adminHost,
  port: settings.adminPort,
  logger,
})

let activeSocket = null
let starting = false
let reconnectTimer = null
let refreshQueue = Promise.resolve()

async function startSocket() {
  if (starting) return
  starting = true
  runtime.setConnection('connecting', 'Conectando con WhatsApp…')
  try {
    const { state: authState, saveCreds } = await useMultiFileAuthState(settings.authDir)
    const { version, isLatest } = await fetchLatestBaileysVersion()
    logger.info({ version: version.join('.'), isLatest }, 'Using WhatsApp Web version')

    const socket = makeWASocket({
      auth: {
        creds: authState.creds,
        keys: makeCacheableSignalKeyStore(authState.keys, whatsappLogger),
      },
      emitOwnEvents: false,
      getMessage: async () => undefined,
      logger: whatsappLogger,
      markOnlineOnConnect: false,
      syncFullHistory: false,
      version,
    })
    activeSocket = socket

    socket.ev.on('creds.update', saveCreds)
    socket.ev.on('connection.update', async (update) => {
      if (update.qr) {
        runtime.qrPng = await QRCode.toBuffer(update.qr, {
          errorCorrectionLevel: 'M',
          margin: 2,
          type: 'png',
          width: 420,
        })
        runtime.setConnection('qr', 'Escaneá el código con WhatsApp → Dispositivos vinculados.')
      }

      if (update.connection === 'open') {
        runtime.qrPng = null
        runtime.setConnection('connected', 'Sesión vinculada y escuchando grupos autorizados.')
        await refreshGroups(socket)
      }

      if (update.connection === 'close') {
        runtime.qrPng = null
        const statusCode = disconnectStatus(update.lastDisconnect?.error)
        activeSocket = null
        if (statusCode === DisconnectReason.loggedOut) {
          runtime.setConnection('logged_out', 'WhatsApp cerró la sesión. Se necesita escanear un QR nuevo.')
          logger.error({ statusCode }, 'WhatsApp session logged out')
          return
        }
        runtime.setConnection('disconnected', `Conexión cerrada; reintentando en ${settings.reconnectDelayMs / 1000}s.`)
        logger.warn({ statusCode }, 'WhatsApp connection closed; scheduling reconnect')
        scheduleReconnect()
      }
    })

    socket.ev.on('groups.upsert', () => refreshGroups(socket))
    socket.ev.on('messages.upsert', async (upsert) => {
      if (upsert.type !== 'notify') return
      for (const message of upsert.messages) {
        try {
          await processMessage(socket, message)
        } catch (error) {
          runtime.recordRecent({
            kind: 'unknown',
            project: 'unknown',
            received_at: new Date().toISOString(),
            status: 'error',
          })
          logger.error({ err: error, messageId: message?.key?.id }, 'Failed to process WhatsApp message')
        }
      }
    })
  } catch (error) {
    runtime.setConnection('error', 'No se pudo iniciar la conexión. Se reintentará automáticamente.')
    logger.error({ err: error }, 'Failed to start WhatsApp socket')
    scheduleReconnect()
  } finally {
    starting = false
  }
}

function scheduleReconnect() {
  if (reconnectTimer) return
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null
    startSocket().catch((error) => logger.error({ err: error }, 'Reconnect failed'))
  }, settings.reconnectDelayMs)
}

async function refreshGroups(socket) {
  const operation = refreshQueue.then(() => doRefreshGroups(socket))
  refreshQueue = operation.catch(() => undefined)
  return operation
}

async function doRefreshGroups(socket) {
  try {
    const [participating, mappings] = await Promise.all([
      socket.groupFetchAllParticipating(),
      loadGroupMappings(settings.groupsFile),
    ])
    const groups = Object.values(participating)
    const adminGroup = await adminGroups.ensureGroup(socket, groups)
    const community = await communities.ensureCommunity(
      socket,
      groups,
      adminGroups.coreParticipants(),
    )
    const projectGroups = groups.filter((group) => (
      !adminGroups.isAdminMetadata(group)
      && !communities.isInfrastructureMetadata(group)
    ))
    const { projects, resolutions } = await reconciler.reconcile(projectGroups, mappings)
    for (const resolution of resolutions) {
      if (!resolution.promote_from || !resolution.project) continue
      const moved = await store.promotePendingProject(resolution.promote_from, resolution.project)
      if (moved) {
        logger.info(
          { from: resolution.promote_from, moved, project: resolution.project },
          'Promoted pending WhatsApp intake records',
        )
      }
    }
    runtime.projects = projects
    runtime.groups = [
      adminGroups.summary(adminGroup),
      communities.summary(community),
      ...resolutions,
    ]
      .filter(Boolean)
      .map((resolution) => ({
        ...resolution,
        id: resolution.group_id,
      }))
      .sort((left, right) => String(left.subject).localeCompare(String(right.subject)))
    await ensureProvisionalProjectDrafts()
    await provisionConfiguredGroups(socket, projects, groups)
  } catch (error) {
    logger.warn({ err: error }, 'Could not refresh WhatsApp groups')
  }
}

async function ensureProvisionalProjectDrafts() {
  for (const group of runtime.groups) {
    if (group.status !== 'provisional' || group.project_factory_draft_id) continue
    try {
      group.draft_status = 'creating'
      const result = await projectFactory.ensureDraftForGroup({
        groupId: group.id,
        subject: group.subject,
      })
      await reconciler.attachProjectFactoryDraft(group.id, result.draftId)
      group.project_factory_draft_id = result.draftId
      group.draft_status = 'ready'
      logger.info(
        { created: result.created, draftId: result.draftId, groupId: group.id },
        'Project Factory draft associated with provisional WhatsApp group',
      )
    } catch (error) {
      group.draft_status = 'error'
      logger.warn({ err: error, groupId: group.id }, 'Could not create provisional Project Factory draft')
    }
  }
}

async function provisionConfiguredGroups(socket, projects, groups) {
  const boundProjects = new Set(runtime.groups.map((group) => group.project).filter(Boolean))
  const configuredSubjects = new Map()
  for (const project of projects) {
    if (!project.integration?.createGroup) continue
    const subject = normalizeIdentity(project.integration.subject)
    configuredSubjects.set(subject, (configuredSubjects.get(subject) || 0) + 1)
  }
  for (const project of projects) {
    const integration = project.integration
    if (!integration?.createGroup || boundProjects.has(project.slug)) continue

    try {
      const normalizedSubject = normalizeIdentity(integration.subject)
      if (configuredSubjects.get(normalizedSubject) > 1) {
        logger.error(
          { project: project.slug, subject: integration.subject },
          'Refusing WhatsApp group provisioning because multiple projects use the same subject',
        )
        continue
      }
      const participants = participantJids(integration.participants)
      if (!participants.length) {
        logger.warn({ project: project.slug }, 'WhatsApp group creation enabled without participants')
        continue
      }
      const sameSubject = groups.find(
        (group) => normalizeIdentity(group.subject) === normalizedSubject,
      )
      const existingResolution = sameSubject
        ? runtime.groups.find((item) => item.id === sameSubject.id)
        : null
      if (existingResolution?.status === 'ambiguous'
          || (existingResolution?.project && existingResolution.project !== project.slug)) {
        logger.error(
          {
            boundProject: existingResolution?.project,
            groupId: sameSubject.id,
            project: project.slug,
          },
          'Refusing to rebind an existing WhatsApp group with a conflicting association',
        )
        continue
      }
      const group = sameSubject || await socket.groupCreate(integration.subject, participants)
      if (integration.description && !sameSubject) {
        await socket.groupUpdateDescription(group.id, integration.description)
      }
      const binding = await reconciler.bindCreatedGroup(group, project.slug)
      if (!runtime.groups.some((item) => item.id === group.id)) {
        runtime.groups.push({ ...binding, id: group.id, provisioning: false })
      }
      if (!sameSubject) groups.push(group)
      boundProjects.add(project.slug)
      logger.info(
        { groupId: group.id, project: project.slug, subject: integration.subject },
        sameSubject ? 'Bound existing configured WhatsApp group' : 'Created configured WhatsApp group',
      )
    } catch (error) {
      logger.error({ err: error, project: project.slug }, 'Could not provision configured WhatsApp group')
    }
  }
}

async function processMessage(socket, message) {
  const groupId = message?.key?.remoteJid
  if (!groupId || message.key.fromMe) return

  if (!groupId.endsWith('@g.us')) {
    await processDirectMessage(message)
    return
  }

  if (adminGroups.isAdminGroup(groupId)) {
    const sharedContacts = parseSharedContacts(message.message)
    if (sharedContacts.length) {
      const result = await adminGroups.handleSharedContacts({
        contacts: sharedContacts,
        message,
      })
      if (result.status === 'mariano_registered') await refreshGroups(socket)
      runtime.recordRecent({
        kind: 'admin_contact',
        project: 'whatsapp-group-admin',
        received_at: new Date().toISOString(),
        status: result.status,
      })
      return
    }
    const parsed = parseInboundContent(message.message)
    if (!parsed) return
    if (parsed.kind !== 'text') {
      runtime.recordRecent({
        kind: parsed.kind,
        project: 'whatsapp-group-admin',
        received_at: new Date().toISOString(),
        status: 'ignored_non_text_admin_command',
      })
      return
    }
    const result = await adminGroups.handleMessage({
      createProjectGroup: ({ participants, project, subject }) => createAdminProjectGroup(
        socket,
        { participants, project, subject },
      ),
      message,
      projects: runtime.projects,
      socket,
      text: parsed.text,
    })
    if (result.status === 'mariano_registered') await refreshGroups(socket)
    runtime.recordRecent({
      kind: 'admin',
      project: 'whatsapp-group-admin',
      received_at: new Date().toISOString(),
      status: result.status,
    })
    return
  }

  const parsed = parseInboundContent(message.message)
  if (!parsed) return

  let group = runtime.groups.find((item) => item.id === groupId)
  if (!group) {
    await refreshGroups(socket)
    group = runtime.groups.find((item) => item.id === groupId)
  }
  if (!group) {
    logger.warn({ groupId, messageId: message.key.id }, 'Ignoring a group that could not be reconciled')
    return
  }

  const project = group.inbox_project
  const timestamp = timestampSeconds(message.messageTimestamp)
  const receivedAt = timestamp ? new Date(timestamp * 1000) : new Date()
  const messageId = message.key.id || `${timestamp || Date.now()}-${message.key.participant || 'unknown'}`

  if (await store.exists(project, messageId, receivedAt)) {
    runtime.recordRecent({
      kind: parsed.kind,
      project,
      received_at: receivedAt.toISOString(),
      status: 'duplicate',
    })
    return
  }

  let mediaBuffer = null
  if (parsed.kind === 'audio' || parsed.kind === 'image') {
    mediaBuffer = await downloadMediaMessage(message, 'buffer', {})
  }

  const manifest = {
    schema: 'nienfos.whatsapp-intake.v1',
    source: 'whatsapp-group',
    received_at: new Date().toISOString(),
    whatsapp_timestamp: receivedAt.toISOString(),
    message_id: messageId,
    group_id: groupId,
    group_subject: group?.subject || null,
    participant_id: message.key.participant || null,
    participant_alt_id: message.key.participantAlt || null,
    push_name: message.pushName || null,
    project,
    project_binding_status: group.status,
    target_project: group.project,
    kind: parsed.kind,
    text: parsed.text,
    mime_type: parsed.mimeType,
    audio_seconds: parsed.seconds,
    voice_note: parsed.voiceNote,
  }
  const result = await store.persist({ manifest, mediaBuffer, project, receivedAt })
  runtime.capturedMessages += result.duplicate ? 0 : 1
  runtime.recordRecent({
    kind: parsed.kind,
    project,
    received_at: receivedAt.toISOString(),
    status: result.duplicate ? 'duplicate' : 'stored',
  })
  logger.info(
    {
      groupId,
      kind: parsed.kind,
      messageId,
      project,
      storedPath: path.relative(settings.repoRoot, result.path),
    },
    result.duplicate ? 'WhatsApp message already stored' : 'WhatsApp message stored',
  )
}

async function processDirectMessage(message) {
  const chatId = message?.key?.remoteJid
  if (!isDirectChat(chatId)) return
  if (await adminGroups.roleForMessage(message) !== 'bruno') {
    logger.warn(
      { chatType: jidType(chatId), messageId: message?.key?.id },
      'Ignoring unauthorized direct WhatsApp message',
    )
    return
  }

  const parsed = parseInboundContent(message.message)
  const directive = parsed?.kind === 'text'
    ? parseDirectProjectDirective(parsed.text)
    : null
  if (!parsed || !['audio', 'image', 'text'].includes(parsed.kind)) {
    runtime.recordRecent({
      kind: parsed?.kind || 'unknown',
      project: settings.directInboxProject,
      received_at: new Date().toISOString(),
      status: 'ignored_unsupported_direct_message',
    })
    return
  }

  const timestamp = timestampSeconds(message.messageTimestamp)
  const receivedAt = timestamp ? new Date(timestamp * 1000) : new Date()
  const messageId = message.key.id || `${timestamp || Date.now()}-bruno-direct`
  if (await store.existsInAnyProject(messageId, receivedAt)) {
    runtime.recordRecent({
      kind: parsed.kind,
      project: settings.directInboxProject,
      received_at: receivedAt.toISOString(),
      status: 'duplicate',
    })
    return
  }

  const mediaBuffer = parsed.kind === 'audio' || parsed.kind === 'image'
    ? await downloadMediaMessage(message, 'buffer', {})
    : null
  const manifest = {
    schema: 'nienfos.whatsapp-intake.v1',
    source: 'whatsapp-direct',
    received_at: new Date().toISOString(),
    whatsapp_timestamp: receivedAt.toISOString(),
    message_id: messageId,
    group_id: chatId,
    group_subject: 'Bruno → Nienfos Codex',
    participant_id: chatId,
    participant_alt_id: message.key.remoteJidAlt || null,
    push_name: message.pushName || 'Bruno',
    project: settings.directInboxProject,
    project_binding_status: 'awaiting_transcript_resolution',
    target_project: null,
    kind: parsed.kind,
    text: parsed.text,
    mime_type: parsed.mimeType,
    audio_seconds: parsed.seconds,
    voice_note: parsed.voiceNote,
    project_routing_directive: Boolean(directive),
  }
  const result = await store.persist({
    manifest,
    mediaBuffer,
    project: settings.directInboxProject,
    receivedAt,
  })
  runtime.capturedMessages += result.duplicate ? 0 : 1
  runtime.recordRecent({
    kind: parsed.kind,
    project: settings.directInboxProject,
    received_at: receivedAt.toISOString(),
    status: result.duplicate ? 'duplicate' : 'stored_for_project_resolution',
  })
  logger.info(
    {
      kind: parsed.kind,
      messageId,
      source: 'whatsapp-direct',
      storedPath: path.relative(settings.repoRoot, result.path),
    },
    result.duplicate
      ? 'Direct WhatsApp message already stored'
      : 'Stored Bruno direct WhatsApp message for project resolution',
  )
}

function jidType(jid) {
  return String(jid || '').split('@').at(-1) || 'unknown'
}

async function createAdminProjectGroup(socket, { participants, project, subject }) {
  const duplicate = runtime.groups.find(
    (group) => normalizeIdentity(group.subject) === normalizeIdentity(subject),
  )
  if (duplicate) {
    if (duplicate.project === project.slug) return { id: duplicate.id }
    throw new Error(`A WhatsApp group already uses the subject: ${subject}`)
  }
  const group = await communities.createProjectGroup(socket, { participants, subject })
  const binding = await reconciler.bindCreatedGroup(group, project.slug)
  runtime.groups.push({ ...binding, id: group.id, provisioning: false })
  try {
    await socket.groupUpdateDescription(
      group.id,
      `Canal del proyecto ${project.name || project.slug}. Los textos y audios se incorporan al espacio de trabajo; no se envían respuestas automáticas.`,
    )
  } catch (error) {
    logger.warn(
      { err: error, groupId: group.id, project: project.slug },
      'Created and bound project group, but could not set its description',
    )
  }
  logger.info(
    { groupId: group.id, project: project.slug, subject },
    'Created project group from authorized WhatsApp administration command',
  )
  return group
}

function createRuntimeState() {
  return {
    capturedMessages: 0,
    connection: 'starting',
    detail: 'Iniciando servicio…',
    groups: [],
    projects: [],
    qrPng: null,
    recent: [],
    recordRecent(item) {
      this.recent.unshift(item)
      this.recent = this.recent.slice(0, 30)
    },
    setConnection(connection, detail) {
      this.connection = connection
      this.detail = detail
    },
    snapshot() {
      const labels = {
        connected: 'Conectado',
        connecting: 'Conectando',
        disconnected: 'Desconectado',
        error: 'Error',
        logged_out: 'Sesión cerrada',
        qr: 'Esperando vinculación',
        starting: 'Iniciando',
      }
      return {
        captured_messages: this.capturedMessages,
        connection: this.connection,
        connection_label: labels[this.connection] || this.connection,
        detail: this.detail,
        groups: this.groups,
        qr_available: Boolean(this.qrPng),
        recent: this.recent,
      }
    },
  }
}

function disconnectStatus(error) {
  return error?.output?.statusCode || error?.statusCode || error?.data?.statusCode || null
}

function shutdown(signal) {
  logger.info({ signal }, 'Shutting down WhatsApp intake service')
  if (reconnectTimer) clearTimeout(reconnectTimer)
  activeSocket?.end?.(new Error(`Process received ${signal}`))
  process.exit(0)
}

process.on('SIGINT', () => shutdown('SIGINT'))
process.on('SIGTERM', () => shutdown('SIGTERM'))

await startSocket()

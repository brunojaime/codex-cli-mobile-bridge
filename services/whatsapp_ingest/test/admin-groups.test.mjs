import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, rm, stat, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'

import { AdminGroupManager, parseAdminCommand, resolveProjectHint } from '../src/admin-groups.mjs'

test('parses Mariano registration without treating it as a group command', () => {
  const command = parseAdminCommand('Este es el número de Mariano Muratore: +54 9 11 5555-1234')
  assert.deepEqual(command, {
    type: 'register_mariano',
    phone: '+5491155551234',
  })
})

test('parses a structured project group creation command', () => {
  const command = parseAdminCommand([
    'Crear grupo: Prueba Nienfos',
    'proyecto: Codex CLI Mobile Bridge',
    'clientes: +54 9 11 5555-1111, +54 9 11 5555-2222',
  ].join('\n'))
  assert.deepEqual(command, {
    type: 'create_group',
    subject: 'Prueba Nienfos',
    projectHint: 'Codex CLI Mobile Bridge',
    phones: ['+5491155551111', '+5491155552222'],
  })
})

test('resolves project names with harmless spacing differences', () => {
  const projects = [
    { slug: 'rentid', identifiers: ['rentid'] },
    { slug: 'codex-cli-mobile-bridge', identifiers: ['Codex CLI Mobile Bridge'] },
  ]
  assert.equal(resolveProjectHint('Rent ID', projects)?.project.slug, 'rentid')
})

test('resolves an obvious unique project prefix but never tied matches', () => {
  assert.equal(resolveProjectHint('SHREM', [
    { slug: 'shrem-properties', identifiers: ['SHREM propiedades'] },
  ])?.project.slug, 'shrem-properties')
  assert.equal(resolveProjectHint('SHREM', [
    { slug: 'shrem-a', identifiers: ['SHREM alfa'] },
    { slug: 'shrem-b', identifiers: ['SHREM beta'] },
  ]), null)
})

test('bootstraps the private admin group and executes only authorized commands', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-admin-group-'))
  context.after(() => rm(root, { recursive: true, force: true }))
  const dataDir = path.join(root, 'data')
  const messageDir = path.join(dataDir, 'inbox', 'codex', 'record')
  await mkdir(messageDir, { recursive: true })
  await writeFile(path.join(messageDir, 'message.json'), JSON.stringify({
    participant_alt_id: '5491155551000@s.whatsapp.net',
    participant_id: 'bruno-device@lid',
    push_name: 'Bruno',
  }))

  const calls = []
  const socket = {
    async groupCreate(subject, participants) {
      calls.push(['create', subject, participants])
      return { id: 'admin@g.us', subject }
    },
    async groupParticipantsUpdate(groupId, participants, operation) {
      calls.push(['participants', groupId, participants, operation])
    },
    async groupUpdateDescription(groupId) {
      calls.push(['description', groupId])
    },
  }
  const stateFile = path.join(dataDir, 'admin-group.json')
  const manager = new AdminGroupManager({
    dataDir,
    stateFile,
    subject: 'Nienfos · Alta de grupos',
  })
  const group = await manager.ensureGroup(socket, [])
  assert.equal(group.id, 'admin@g.us')
  assert.deepEqual(calls[0], [
    'create',
    'Nienfos · Alta de grupos',
    ['5491155551000@s.whatsapp.net'],
  ])
  assert.equal((await stat(stateFile)).mode & 0o777, 0o600)

  const baseMessage = {
    key: {
      participant: 'bruno-device@lid',
      participantAlt: '5491155551000@s.whatsapp.net',
      remoteJid: 'admin@g.us',
    },
  }
  const registration = await manager.handleMessage({
    createProjectGroup: () => assert.fail('registration must not create a project group'),
    message: { ...baseMessage, key: { ...baseMessage.key, id: 'register-mariano' } },
    projects: [],
    socket,
    text: 'Mariano Muratore: +54 9 11 5555-2000',
  })
  assert.equal(registration.status, 'mariano_registered')
  assert.equal(calls.some((call) => call[0] === 'participants'), false)

  let requested = null
  const creation = await manager.handleMessage({
    createProjectGroup: async (request) => {
      requested = request
      return { id: 'project@g.us' }
    },
    message: { ...baseMessage, key: { ...baseMessage.key, id: 'create-project' } },
    projects: [{
      identifiers: ['rentid'],
      name: 'RentID',
      slug: 'rentid',
    }],
    socket,
    text: [
      'Crear grupo: Rent ID cliente',
      'proyecto: Rent ID',
      'clientes: +54 9 11 5555-3000',
    ].join('\n'),
  })
  assert.equal(creation.status, 'group_created')
  assert.equal(requested.subject, 'Rent ID cliente')
  assert.equal(requested.project.slug, 'rentid')
  assert.deepEqual(requested.participants, [
    '5491155551000@s.whatsapp.net',
    '5491155552000@s.whatsapp.net',
    '5491155553000@s.whatsapp.net',
  ])

  requested = null
  const unauthorized = await manager.handleMessage({
    createProjectGroup: async (request) => { requested = request },
    message: {
      key: {
        id: 'unauthorized',
        participant: 'intruder@lid',
        participantAlt: '5491155559999@s.whatsapp.net',
        remoteJid: 'admin@g.us',
      },
    },
    projects: [{ identifiers: ['rentid'], slug: 'rentid' }],
    socket,
    text: 'Crear grupo: No autorizado\nproyecto: rentid',
  })
  assert.equal(unauthorized.status, 'unauthorized')
  assert.equal(requested, null)

  const storedState = JSON.parse(await readFile(stateFile, 'utf8'))
  assert.equal(storedState.group_id, 'admin@g.us')
  assert.equal(storedState.people.mariano.phone_jid, '5491155552000@s.whatsapp.net')
})

test('registers a shared Mariano contact without adding anyone to the admin group', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-admin-contact-'))
  context.after(() => rm(root, { recursive: true, force: true }))
  const dataDir = path.join(root, 'data')
  const messageDir = path.join(dataDir, 'inbox', 'codex', 'record')
  await mkdir(messageDir, { recursive: true })
  await writeFile(path.join(messageDir, 'message.json'), JSON.stringify({
    participant_alt_id: '5491155551000@s.whatsapp.net',
    participant_id: 'bruno-device@lid',
    push_name: 'Bruno',
  }))
  const stateFile = path.join(dataDir, 'admin-group.json')
  const manager = new AdminGroupManager({ dataDir, stateFile, subject: 'Admin' })
  await manager.ensureGroup({
    groupCreate: async () => ({ id: 'admin@g.us', subject: 'Admin' }),
    groupUpdateDescription: async () => undefined,
  }, [])
  const result = await manager.handleSharedContacts({
    contacts: [{ displayName: 'Mariano Muratore', phone: '+54 9 11 5555-2000' }],
    message: {
      key: {
        id: 'shared-contact',
        participant: 'bruno-device@lid',
        participantAlt: '5491155551000@s.whatsapp.net',
        remoteJid: 'admin@g.us',
      },
    },
  })
  assert.equal(result.status, 'mariano_registered')
  assert.deepEqual(manager.coreParticipants(), [
    '5491155551000@s.whatsapp.net',
    '5491155552000@s.whatsapp.net',
  ])
})

test('accepts one authorized contact card even when WhatsApp omits its display name', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-admin-unnamed-contact-'))
  context.after(() => rm(root, { recursive: true, force: true }))
  const dataDir = path.join(root, 'data')
  const messageDir = path.join(dataDir, 'inbox', 'codex', 'record')
  await mkdir(messageDir, { recursive: true })
  await writeFile(path.join(messageDir, 'message.json'), JSON.stringify({
    participant_alt_id: '5491155551000@s.whatsapp.net',
    participant_id: 'bruno-device@lid',
    push_name: 'Bruno',
  }))
  const manager = new AdminGroupManager({
    dataDir,
    stateFile: path.join(dataDir, 'admin-group.json'),
    subject: 'Admin',
  })
  await manager.ensureGroup({
    groupCreate: async () => ({ id: 'admin@g.us', subject: 'Admin' }),
    groupUpdateDescription: async () => undefined,
  }, [])
  const result = await manager.handleSharedContacts({
    contacts: [{ displayName: null, phone: '+54 9 11 5555-2000' }],
    message: {
      key: {
        id: 'unnamed-contact',
        participant: 'bruno-device@lid',
        participantAlt: '5491155551000@s.whatsapp.net',
        remoteJid: 'admin@g.us',
      },
    },
  })
  assert.equal(result.status, 'mariano_registered')
  assert.equal(manager.coreParticipants().length, 2)
})

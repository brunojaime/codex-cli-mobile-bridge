import assert from 'node:assert/strict'
import { mkdtemp, mkdir, readFile, rm, writeFile } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import test from 'node:test'

import {
  discoverProjects,
  normalizeIdentity,
  participantJids,
  ProjectReconciler,
} from '../src/project-reconciler.mjs'

async function fixture(t) {
  const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-reconciler-'))
  t.after(() => rm(root, { recursive: true, force: true }))
  const projectsRoot = path.join(root, 'Projects')
  const dataDir = path.join(root, 'data')
  await mkdir(projectsRoot)
  return {
    dataDir,
    projectsRoot,
    reconciler: new ProjectReconciler({
      projectsRoot,
      registryFile: path.join(dataDir, 'registry.json'),
    }),
  }
}

async function project(projectsRoot, slug, manifest = null, integration = null) {
  const directory = path.join(projectsRoot, slug)
  await mkdir(path.join(directory, '.codex'), { recursive: true })
  if (manifest) await writeFile(path.join(directory, '.codex', 'project.yaml'), manifest)
  if (integration) {
    await mkdir(path.join(directory, '.codex', 'integrations'), { recursive: true })
    await writeFile(
      path.join(directory, '.codex', 'integrations', 'whatsapp.json'),
      JSON.stringify(integration),
    )
  }
}

test('matches a discovered group to a unique project identity and remembers its group id', async (t) => {
  const { projectsRoot, reconciler } = await fixture(t)
  await project(projectsRoot, 'rentid', 'schema_version: 1\nname: RentID\nslug: rentid\n')

  const first = await reconciler.reconcile([{ id: '123@g.us', subject: 'Nienfos · RentID' }])
  assert.equal(first.resolutions[0].status, 'matched')
  assert.equal(first.resolutions[0].project, 'rentid')
  assert.equal(first.resolutions[0].source, 'exact_identity')

  const renamed = await reconciler.reconcile([{ id: '123@g.us', subject: 'Nombre nuevo' }])
  assert.equal(renamed.resolutions[0].project, 'rentid')
  assert.equal(renamed.resolutions[0].source, 'exact_identity')
})

test('uses stable pending inboxes and retries provisional matches', async (t) => {
  const { projectsRoot, reconciler } = await fixture(t)
  const first = await reconciler.reconcile([{ id: '456@g.us', subject: 'Cliente nuevo' }])
  assert.equal(first.resolutions[0].status, 'provisional')
  assert.match(first.resolutions[0].inbox_project, /^pending-cliente-nuevo-/)

  await project(projectsRoot, 'cliente-nuevo')
  const second = await reconciler.reconcile([{ id: '456@g.us', subject: 'Cliente nuevo' }])
  assert.equal(second.resolutions[0].status, 'matched')
  assert.equal(second.resolutions[0].project, 'cliente-nuevo')
  assert.equal(second.resolutions[0].promote_from, first.resolutions[0].inbox_project)
})

test('does not guess when aliases make a group ambiguous', async (t) => {
  const { projectsRoot, reconciler } = await fixture(t)
  const integration = { version: 1, aliases: ['Puerto'] }
  await project(projectsRoot, 'puerto-uno', null, integration)
  await project(projectsRoot, 'puerto-dos', null, integration)
  const result = await reconciler.reconcile([{ id: '789@g.us', subject: 'Puerto' }])
  assert.equal(result.resolutions[0].status, 'ambiguous')
  assert.deepEqual(result.resolutions[0].candidates, ['puerto-dos', 'puerto-uno'])
})

test('manual bindings override names but validate that the project exists', async (t) => {
  const { projectsRoot, reconciler } = await fixture(t)
  await project(projectsRoot, 'real-project')
  const manual = new Map([['123@g.us', { project: 'real-project' }]])
  const result = await reconciler.reconcile([{ id: '123@g.us', subject: 'Nada que ver' }], manual)
  assert.equal(result.resolutions[0].project, 'real-project')
  assert.equal(result.resolutions[0].source, 'manual')
})

test('discovers nested v2 manifests and opt-in group provisioning configuration', async (t) => {
  const { projectsRoot } = await fixture(t)
  await project(
    projectsRoot,
    'nienfos-gestion',
    'schema_version: 2\nproject:\n  name: Nienfos Gestión\n  slug: nienfos-gestion\n',
    {
      version: 1,
      enabled: true,
      create_group: true,
      participants: ['+54 9 11 1234-5678'],
    },
  )
  const projects = await discoverProjects(projectsRoot)
  assert.deepEqual(projects[0].identifiers.sort(), ['nienfos gestion', 'nienfos nienfos gestion'])
  assert.equal(projects[0].integration.createGroup, true)
  assert.equal(projects[0].integration.subject, 'Nienfos · Nienfos Gestión')
})

test('discovers a legacy project whose .codex entry is a file', async (t) => {
  const { projectsRoot } = await fixture(t)
  const directory = path.join(projectsRoot, 'legacy-project')
  await mkdir(directory)
  await writeFile(path.join(directory, '.codex'), '')

  const projects = await discoverProjects(projectsRoot)

  assert.equal(projects.length, 1)
  assert.equal(projects[0].slug, 'legacy-project')
  assert.equal(projects[0].name, 'legacy-project')
  assert.equal(projects[0].integration, null)
})

test('normalizes human names and validates participant phone numbers', () => {
  assert.equal(normalizeIdentity('  Gestión & Ventas '), 'gestion y ventas')
  assert.deepEqual(participantJids(['+54 9 11 1234-5678']), ['5491112345678@s.whatsapp.net'])
  assert.throws(() => participantJids(['123']))
})

test('writes an auditable registry atomically', async (t) => {
  const { dataDir, reconciler } = await fixture(t)
  await reconciler.reconcile([{ id: '123@g.us', subject: 'Proyecto' }])
  const registry = JSON.parse(await readFile(path.join(dataDir, 'registry.json'), 'utf8'))
  assert.equal(registry.version, 1)
  assert.equal(registry.groups['123@g.us'].status, 'provisional')
})

test('persists the Project Factory draft link for a provisional group', async (t) => {
  const { dataDir, reconciler } = await fixture(t)
  await reconciler.reconcile([{ id: '123@g.us', subject: 'Proyecto' }])
  await reconciler.attachProjectFactoryDraft('123@g.us', 'pf-draft-123')
  const registry = JSON.parse(await readFile(path.join(dataDir, 'registry.json'), 'utf8'))
  assert.equal(registry.groups['123@g.us'].project_factory_draft_id, 'pf-draft-123')
})

test('marks disappeared groups inactive without deleting their binding', async (t) => {
  const { dataDir, projectsRoot, reconciler } = await fixture(t)
  await project(projectsRoot, 'cliente')
  await reconciler.reconcile([{ id: '123@g.us', subject: 'Cliente' }])
  await reconciler.reconcile([])
  let registry = JSON.parse(await readFile(path.join(dataDir, 'registry.json'), 'utf8'))
  assert.equal(registry.groups['123@g.us'].status, 'inactive')
  assert.equal(registry.groups['123@g.us'].project, 'cliente')

  const returned = await reconciler.reconcile([{ id: '123@g.us', subject: 'Otro nombre' }])
  assert.equal(returned.resolutions[0].status, 'matched')
  assert.equal(returned.resolutions[0].project, 'cliente')
  registry = JSON.parse(await readFile(path.join(dataDir, 'registry.json'), 'utf8'))
  assert.equal(registry.groups['123@g.us'].active, true)
  assert.equal(registry.groups['123@g.us'].missing_since, null)
})

import { createHash } from 'node:crypto'
import { mkdir, readFile, readdir, rename, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { parse as parseYaml } from 'yaml'

const PROJECT_SLUG = /^[a-z0-9][a-z0-9_-]{0,79}$/

export class ProjectReconciler {
  constructor({ projectsRoot, registryFile, logger = null }) {
    this.projectsRoot = path.resolve(projectsRoot)
    this.registryFile = path.resolve(registryFile)
    this.logger = logger
    this.queue = Promise.resolve()
  }

  reconcile(groups, manualMappings = new Map()) {
    const operation = this.queue.then(() => this.#reconcile(groups, manualMappings))
    this.queue = operation.catch(() => undefined)
    return operation
  }

  async #reconcile(groups, manualMappings) {
    const [projects, registry] = await Promise.all([
      discoverProjects(this.projectsRoot),
      readRegistry(this.registryFile),
    ])
    const projectBySlug = new Map(projects.map((project) => [project.slug, project]))
    const now = new Date().toISOString()
    const resolutions = []

    for (const group of groups) {
      const previous = registry.groups[group.id]
      const manual = manualMappings.get(group.id)
      const resolution = resolveGroup({
        group,
        manual,
        previous,
        projectBySlug,
        projects,
      })
      const firstSeenAt = previous?.first_seen_at || now
      const matchedAt = resolution.project
        ? previous?.project === resolution.project && previous?.matched_at
          ? previous.matched_at
          : now
        : null
      const persisted = {
        active: true,
        group_id: group.id,
        subject: group.subject || null,
        status: resolution.status,
        source: resolution.source,
        project: resolution.project,
        inbox_project: resolution.inboxProject,
        candidates: resolution.candidates,
        first_seen_at: firstSeenAt,
        last_seen_at: now,
        matched_at: matchedAt,
        project_factory_draft_id: previous?.project_factory_draft_id || null,
        missing_since: null,
      }
      registry.groups[group.id] = persisted
      resolutions.push({
        ...persisted,
        promote_from: resolution.project && previous?.inbox_project?.startsWith('pending-')
          && previous.inbox_project !== resolution.inboxProject
          ? previous.inbox_project
          : null,
        provisioning: false,
      })
    }

    const observedGroupIds = new Set(groups.map((group) => group.id))
    for (const [groupId, entry] of Object.entries(registry.groups)) {
      if (observedGroupIds.has(groupId) || entry.active === false) continue
      registry.groups[groupId] = {
        ...entry,
        active: false,
        missing_since: now,
        status: 'inactive',
      }
    }

    registry.updated_at = now
    await writeRegistry(this.registryFile, registry)
    return { projects, resolutions }
  }

  async bindCreatedGroup(group, projectSlug) {
    const operation = this.queue.then(async () => {
      const registry = await readRegistry(this.registryFile)
      const now = new Date().toISOString()
      registry.groups[group.id] = {
        active: true,
        group_id: group.id,
        subject: group.subject || null,
        status: 'matched',
        source: 'provisioned',
        project: projectSlug,
        inbox_project: projectSlug,
        candidates: [projectSlug],
        first_seen_at: now,
        last_seen_at: now,
        matched_at: now,
        project_factory_draft_id: null,
        missing_since: null,
      }
      registry.updated_at = now
      await writeRegistry(this.registryFile, registry)
      return registry.groups[group.id]
    })
    this.queue = operation.catch(() => undefined)
    return operation
  }

  async attachProjectFactoryDraft(groupId, draftId) {
    const operation = this.queue.then(async () => {
      const registry = await readRegistry(this.registryFile)
      const entry = registry.groups[groupId]
      if (!entry) throw new Error(`Cannot attach a draft to unknown group ${groupId}`)
      entry.project_factory_draft_id = draftId
      registry.updated_at = new Date().toISOString()
      await writeRegistry(this.registryFile, registry)
      return entry
    })
    this.queue = operation.catch(() => undefined)
    return operation
  }
}

export async function discoverProjects(projectsRoot) {
  let entries
  try {
    entries = await readdir(projectsRoot, { withFileTypes: true })
  } catch (error) {
    if (error?.code === 'ENOENT') return []
    throw error
  }

  const projects = []
  for (const entry of entries) {
    if (!entry.isDirectory() || entry.name.startsWith('.') || !PROJECT_SLUG.test(entry.name)) continue
    const projectDir = path.join(projectsRoot, entry.name)
    const manifest = await readYaml(path.join(projectDir, '.codex', 'project.yaml'))
    const integration = await readJson(path.join(projectDir, '.codex', 'integrations', 'whatsapp.json'))
    const manifestProject = manifest?.project && typeof manifest.project === 'object'
      ? manifest.project
      : manifest
    const name = stringValue(manifestProject?.name) || entry.name
    const declaredSlug = stringValue(manifestProject?.slug)
    const aliases = Array.isArray(integration?.aliases)
      ? integration.aliases.map(stringValue).filter(Boolean)
      : []
    const normalizedIntegration = normalizeIntegration(integration, entry.name, name)
    const identifiers = new Set([
      entry.name,
      name,
      declaredSlug,
      normalizedIntegration?.subject,
      ...aliases,
    ].filter(Boolean).map(normalizeIdentity))
    projects.push({
      aliases,
      identifiers: [...identifiers].filter(Boolean),
      integration: normalizedIntegration,
      name,
      path: projectDir,
      slug: entry.name,
    })
  }
  return projects.sort((left, right) => left.slug.localeCompare(right.slug))
}

export function resolveGroup({ group, manual, previous, projectBySlug, projects }) {
  if (manual) {
    if (projectBySlug.has(manual.project)) {
      return matched(manual.project, 'manual')
    }
    return pending(group, 'project_missing', 'manual_missing', [manual.project])
  }

  if (previous?.project && projectBySlug.has(previous.project)) {
    return matched(previous.project, previous.source || 'registry')
  }

  const identities = groupIdentities(group.subject)
  const candidates = projects
    .filter((project) => project.identifiers.some((identifier) => identities.has(identifier)))
    .map((project) => project.slug)

  if (candidates.length === 1) return matched(candidates[0], 'exact_identity')
  if (candidates.length > 1) return pending(group, 'ambiguous', 'exact_identity', candidates)
  return pending(group, 'provisional', 'unmatched', [])
}

export function normalizeIdentity(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/&/g, ' y ')
    .replace(/[^a-z0-9]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ')
}

export function participantJids(participants) {
  return [...new Set((participants || []).map((value) => {
    const digits = String(value || '').replace(/\D/g, '')
    if (digits.length < 8 || digits.length > 15) {
      throw new Error(`Invalid WhatsApp participant number: ${value}`)
    }
    return `${digits}@s.whatsapp.net`
  }))]
}

function matched(project, source) {
  return {
    candidates: [project],
    inboxProject: project,
    project,
    source,
    status: 'matched',
  }
}

function pending(group, status, source, candidates) {
  return {
    candidates,
    inboxProject: pendingSlug(group),
    project: null,
    source,
    status,
  }
}

function pendingSlug(group) {
  const subject = normalizeIdentity(group.subject).replace(/ /g, '-').slice(0, 38) || 'grupo'
  const suffix = createHash('sha256').update(String(group.id)).digest('hex').slice(0, 10)
  return `pending-${subject}-${suffix}`.slice(0, 79)
}

function groupIdentities(subject) {
  const normalized = normalizeIdentity(subject)
  const identities = new Set([normalized])
  const withoutNienfos = normalized.replace(/^nienfos\s+/, '')
  if (withoutNienfos) identities.add(withoutNienfos)
  return identities
}

function normalizeIntegration(value, slug, name) {
  if (!value || value.version !== 1) return null
  const participants = Array.isArray(value.participants) ? value.participants.map(String) : []
  return {
    createGroup: value.enabled === true && value.create_group === true,
    description: stringValue(value.description),
    participants,
    subject: stringValue(value.subject) || `Nienfos · ${name || slug}`,
  }
}

async function readYaml(filename) {
  try {
    return parseYaml(await readFile(filename, 'utf8'))
  } catch (error) {
    // Some legacy projects contain a file named `.codex` instead of the
    // directory used by current project metadata. Treat those projects as
    // having no manifest rather than aborting discovery for every project.
    if (error?.code === 'ENOENT' || error?.code === 'ENOTDIR') return null
    throw new Error(`Could not read ${filename}: ${error.message}`, { cause: error })
  }
}

async function readJson(filename) {
  try {
    return JSON.parse(await readFile(filename, 'utf8'))
  } catch (error) {
    if (error?.code === 'ENOENT' || error?.code === 'ENOTDIR') return null
    throw new Error(`Could not read ${filename}: ${error.message}`, { cause: error })
  }
}

async function readRegistry(filename) {
  try {
    const value = JSON.parse(await readFile(filename, 'utf8'))
    if (value?.version !== 1 || !value.groups || typeof value.groups !== 'object') {
      throw new Error('registry must contain version 1 and a groups object')
    }
    return value
  } catch (error) {
    if (error?.code === 'ENOENT') return { version: 1, groups: {}, updated_at: null }
    throw error
  }
}

async function writeRegistry(filename, registry) {
  await mkdir(path.dirname(filename), { recursive: true, mode: 0o700 })
  const temporary = `${filename}.${process.pid}.${Date.now()}.tmp`
  await writeFile(temporary, `${JSON.stringify(registry, null, 2)}\n`, { mode: 0o600 })
  await rename(temporary, filename)
}

function stringValue(value) {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

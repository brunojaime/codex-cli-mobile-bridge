import { readFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const serviceRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const repoRoot = path.resolve(serviceRoot, '..', '..')

function envPort(name, fallback) {
  const value = Number.parseInt(process.env[name] || '', 10)
  if (!Number.isInteger(value) || value < 1 || value > 65535) return fallback
  return value
}

export function loadSettings() {
  const dataDir = path.resolve(
    process.env.WHATSAPP_DATA_DIR || path.join(repoRoot, '.data', 'whatsapp_ingest'),
  )

  return {
    adminHost: process.env.WHATSAPP_ADMIN_HOST || '127.0.0.1',
    adminPort: envPort('WHATSAPP_ADMIN_PORT', 8787),
    authDir: path.resolve(process.env.WHATSAPP_AUTH_DIR || path.join(dataDir, 'auth')),
    dataDir,
    projectsRoot: path.resolve(
      process.env.WHATSAPP_PROJECTS_ROOT || path.join(repoRoot, '..'),
    ),
    projectFactoryUrl: (process.env.WHATSAPP_PROJECT_FACTORY_URL || 'http://127.0.0.1:8000')
      .replace(/\/+$/, ''),
    registryFile: path.resolve(
      process.env.WHATSAPP_GROUP_REGISTRY_FILE || path.join(dataDir, 'group-registry.json'),
    ),
    groupsFile: path.resolve(
      process.env.WHATSAPP_GROUPS_FILE || path.join(serviceRoot, 'config', 'groups.json'),
    ),
    logLevel: process.env.WHATSAPP_LOG_LEVEL || 'info',
    reconnectDelayMs: Math.max(
      1_000,
      Number.parseInt(process.env.WHATSAPP_RECONNECT_DELAY_MS || '5000', 10) || 5_000,
    ),
    repoRoot,
    serviceRoot,
  }
}

export async function loadGroupMappings(groupsFile) {
  let raw
  try {
    raw = await readFile(groupsFile, 'utf8')
  } catch (error) {
    if (error?.code === 'ENOENT') return new Map()
    throw error
  }

  const payload = JSON.parse(raw)
  if (payload?.version !== 1 || typeof payload.groups !== 'object' || !payload.groups) {
    throw new Error('groups.json must contain {"version":1,"groups":{...}}')
  }

  const mappings = new Map()
  for (const [groupId, entry] of Object.entries(payload.groups)) {
    if (!groupId.endsWith('@g.us')) {
      throw new Error(`Invalid WhatsApp group id: ${groupId}`)
    }
    if (!entry || entry.enabled === false) continue
    const project = String(entry.project || '').trim()
    if (!/^[a-z0-9][a-z0-9_-]{0,79}$/.test(project)) {
      throw new Error(`Invalid project slug for ${groupId}: ${project}`)
    }
    mappings.set(groupId, { enabled: true, project })
  }
  return mappings
}

export { repoRoot, serviceRoot }

import { mkdir, readdir, rename, rm, rmdir, stat, writeFile } from 'node:fs/promises'
import path from 'node:path'

export class IntakeStore {
  constructor(dataDir) {
    this.dataDir = path.resolve(dataDir)
    this.inboxDir = path.join(this.dataDir, 'inbox')
    this.processingDir = path.join(this.dataDir, 'processing')
  }

  async initialize() {
    await mkdir(this.inboxDir, { recursive: true, mode: 0o700 })
    await mkdir(this.processingDir, { recursive: true, mode: 0o700 })
  }

  destinationFor(project, messageId, receivedAt = new Date()) {
    validateProjectSlug(project)
    const date = receivedAt.toISOString().slice(0, 10)
    return path.join(this.inboxDir, project, date, safeComponent(messageId))
  }

  async exists(project, messageId, receivedAt = new Date()) {
    const readyPath = path.join(this.destinationFor(project, messageId, receivedAt), 'READY')
    try {
      await stat(readyPath)
      return true
    } catch (error) {
      if (error?.code === 'ENOENT') return false
      throw error
    }
  }

  async persist({ manifest, mediaBuffer = null, project, receivedAt = new Date() }) {
    const destination = this.destinationFor(project, manifest.message_id, receivedAt)
    if (await this.exists(project, manifest.message_id, receivedAt)) {
      return { duplicate: true, path: destination }
    }

    const tempName = `${safeComponent(manifest.message_id)}-${process.pid}-${Date.now()}`
    const temporary = path.join(this.processingDir, tempName)
    await mkdir(temporary, { recursive: false, mode: 0o700 })

    try {
      const materialized = { ...manifest }
      if (manifest.text) {
        await writeFile(path.join(temporary, 'message.txt'), `${manifest.text}\n`, {
          encoding: 'utf8',
          mode: 0o600,
        })
        materialized.text_file = 'message.txt'
      }

      if (mediaBuffer) {
        const filename = `audio-original${extensionForMime(manifest.mime_type)}`
        await writeFile(path.join(temporary, filename), mediaBuffer, { mode: 0o600 })
        materialized.media_file = filename
        materialized.media_bytes = mediaBuffer.length
      }

      await writeFile(
        path.join(temporary, 'message.json'),
        `${JSON.stringify(materialized, null, 2)}\n`,
        { encoding: 'utf8', mode: 0o600 },
      )
      await writeFile(path.join(temporary, 'READY'), '', { mode: 0o600 })

      await mkdir(path.dirname(destination), { recursive: true, mode: 0o700 })
      try {
        await rename(temporary, destination)
      } catch (error) {
        if (error?.code === 'EEXIST' || error?.code === 'ENOTEMPTY') {
          await rm(temporary, { recursive: true, force: true })
          return { duplicate: true, path: destination }
        }
        throw error
      }
      return { duplicate: false, path: destination }
    } catch (error) {
      await rm(temporary, { recursive: true, force: true })
      throw error
    }
  }

  async promotePendingProject(pendingProject, project) {
    validateProjectSlug(pendingProject)
    validateProjectSlug(project)
    if (!pendingProject.startsWith('pending-') || pendingProject === project) return 0

    const sourceRoot = path.join(this.inboxDir, pendingProject)
    let dates
    try {
      dates = await readdir(sourceRoot, { withFileTypes: true })
    } catch (error) {
      if (error?.code === 'ENOENT') return 0
      throw error
    }

    let moved = 0
    for (const date of dates) {
      if (!date.isDirectory()) continue
      const sourceDate = path.join(sourceRoot, date.name)
      const destinationDate = path.join(this.inboxDir, project, date.name)
      await mkdir(destinationDate, { recursive: true, mode: 0o700 })
      for (const message of await readdir(sourceDate, { withFileTypes: true })) {
        if (!message.isDirectory()) continue
        try {
          await rename(path.join(sourceDate, message.name), path.join(destinationDate, message.name))
          moved += 1
        } catch (error) {
          if (error?.code !== 'EEXIST' && error?.code !== 'ENOTEMPTY') throw error
        }
      }
      await rmdir(sourceDate).catch((error) => {
        if (error?.code !== 'ENOTEMPTY' && error?.code !== 'ENOENT') throw error
      })
    }
    await rmdir(sourceRoot).catch((error) => {
      if (error?.code !== 'ENOTEMPTY' && error?.code !== 'ENOENT') throw error
    })
    return moved
  }
}

export function extensionForMime(mimeType) {
  const normalized = String(mimeType || '').split(';', 1)[0].trim().toLowerCase()
  return {
    'audio/aac': '.aac',
    'audio/amr': '.amr',
    'audio/mp4': '.m4a',
    'audio/mpeg': '.mp3',
    'audio/ogg': '.ogg',
    'audio/opus': '.opus',
  }[normalized] || '.bin'
}

function validateProjectSlug(project) {
  if (!/^[a-z0-9][a-z0-9_-]{0,79}$/.test(project)) {
    throw new Error(`Invalid project slug: ${project}`)
  }
}

function safeComponent(value) {
  const safe = String(value || '').replace(/[^A-Za-z0-9._-]/g, '_').slice(0, 160)
  return safe || 'unknown-message'
}

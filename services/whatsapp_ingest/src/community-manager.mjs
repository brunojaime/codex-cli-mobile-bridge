import { mkdir, readFile, rename, writeFile } from 'node:fs/promises'
import path from 'node:path'

import { normalizeIdentity } from './project-reconciler.mjs'

const STATE_VERSION = 1

export class CommunityManager {
  constructor({ logger = null, stateFile, subject }) {
    this.logger = logger
    this.stateFile = path.resolve(stateFile)
    this.subject = String(subject || 'Nienfos').trim()
    this.state = null
  }

  async ensureCommunity(socket, groups, participants) {
    if ((participants || []).length < 2) return null
    const state = await this.#loadState()
    let community = state.community_id
      ? groups.find((group) => group.id === state.community_id)
      : groups.find((group) => (
          group.isCommunity
          && normalizeIdentity(group.subject) === normalizeIdentity(state.subject)
        ))
    if (!community && state.community_id) {
      try {
        community = await socket.groupMetadata(state.community_id)
      } catch {
        community = null
      }
    }
    if (!community) {
      community = await socket.communityCreate(
        state.subject,
        'Comunidad de proyectos de Nienfos. Cada proyecto utiliza un grupo privado independiente.',
      )
      if (!community?.id) throw new Error('WhatsApp did not return the created community identifier.')
      state.community_id = community.id
      state.created_at = new Date().toISOString()
      await this.#saveState()
      this.logger?.info?.(
        { communityId: community.id, subject: state.subject },
        'Created Nienfos WhatsApp community',
      )
    }
    if (!(state.infrastructure_group_ids || []).length) {
      const discovery = await findCommunityInfrastructure(socket, groups, community.id)
      state.announcement_group_id = discovery.announcement.id
      state.infrastructure_group_ids = discovery.infrastructureGroupIds
      state.membership_mode = 'project_groups'
      await this.#saveState()
    }
    return community
  }

  async createProjectGroup(socket, { participants, subject }) {
    if (!this.state?.community_id) {
      throw new Error('The Nienfos WhatsApp community is not ready.')
    }
    const group = await socket.communityCreateGroup(
      subject,
      [...new Set(participants)],
      this.state.community_id,
    )
    if (!group?.id) throw new Error('WhatsApp did not return the created project group identifier.')
    return group
  }

  isInfrastructureMetadata(group) {
    if (!group) return false
    return Boolean(
      group.isCommunity
      || group.isCommunityAnnounce
      || (this.state?.community_id && group.id === this.state.community_id)
      || (this.state?.announcement_group_id && group.id === this.state.announcement_group_id)
      || (this.state?.infrastructure_group_ids || []).includes(group.id)
    )
  }

  summary(community) {
    if (!community) return null
    return {
      active: true,
      candidates: [],
      group_id: community.id,
      id: community.id,
      inbox_project: 'whatsapp-community-admin',
      project: null,
      source: 'community_control',
      status: 'community',
      subject: community.subject || this.subject,
    }
  }

  async #loadState() {
    if (this.state) return this.state
    try {
      const value = JSON.parse(await readFile(this.stateFile, 'utf8'))
      if (value?.version !== STATE_VERSION || !value.subject) {
        throw new Error('Invalid WhatsApp community state.')
      }
      this.state = value
      return value
    } catch (error) {
      if (error?.code !== 'ENOENT') throw error
    }
    this.state = {
      version: STATE_VERSION,
      subject: this.subject,
      community_id: null,
      created_at: null,
      initial_participants_added: false,
      participants_added_at: null,
      announcement_group_id: null,
      infrastructure_group_ids: [],
      participant_add_error: null,
      membership_mode: 'project_groups',
    }
    await this.#saveState()
    return this.state
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

async function findCommunityInfrastructure(socket, groups, communityId) {
  const observed = groups.find((group) => (
    group.isCommunityAnnounce && group.linkedParent === communityId
  ))
  const linked = await socket.communityFetchLinkedGroups(communityId)
  const infrastructureGroupIds = []
  let announcement = observed || null
  for (const candidate of linked?.linkedGroups || []) {
    if (!candidate?.id) continue
    const metadata = await socket.groupMetadata(candidate.id)
    if (
      metadata?.isCommunityAnnounce
      || normalizeIdentity(metadata?.subject) === 'general'
    ) {
      infrastructureGroupIds.push(metadata.id)
    }
    if (!announcement && metadata?.isCommunityAnnounce) announcement = metadata
  }
  if (!announcement) throw new Error('Could not locate the community announcement group.')
  if (!infrastructureGroupIds.includes(announcement.id)) {
    infrastructureGroupIds.push(announcement.id)
  }
  return { announcement, infrastructureGroupIds }
}

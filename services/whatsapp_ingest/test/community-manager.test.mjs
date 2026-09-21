import assert from 'node:assert/strict'
import { mkdtemp, readFile, rm, stat } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { test } from 'node:test'

import { CommunityManager } from '../src/community-manager.mjs'

test('waits for both people and then creates the community exactly once', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-community-'))
  context.after(() => rm(root, { recursive: true, force: true }))
  const stateFile = path.join(root, 'community.json')
  const calls = []
  const socket = {
    async communityCreate(subject, description) {
      calls.push(['create', subject, description])
      return { id: 'community@g.us', isCommunity: true, subject }
    },
    async communityFetchLinkedGroups() {
      calls.push(['linked'])
      return { linkedGroups: [{ id: 'announcements@g.us' }] }
    },
    async groupMetadata(id) {
      if (id === 'announcements@g.us') {
        return {
          id,
          isCommunityAnnounce: true,
          linkedParent: 'community@g.us',
          subject: 'Announcements',
        }
      }
      return { id, isCommunity: true, subject: 'Nienfos' }
    },
  }
  const manager = new CommunityManager({ stateFile, subject: 'Nienfos' })
  assert.equal(await manager.ensureCommunity(socket, [], ['bruno@s.whatsapp.net']), null)
  const participants = ['bruno@s.whatsapp.net', 'mariano@s.whatsapp.net']
  const community = await manager.ensureCommunity(socket, [], participants)
  assert.equal(community.id, 'community@g.us')
  assert.deepEqual(calls.map((call) => call[0]), ['create', 'linked'])
  assert.equal((await stat(stateFile)).mode & 0o777, 0o600)

  await manager.ensureCommunity(socket, [], participants)
  assert.deepEqual(calls.map((call) => call[0]), ['create', 'linked'])
  const state = JSON.parse(await readFile(stateFile, 'utf8'))
  assert.equal(state.community_id, 'community@g.us')
  assert.equal(state.initial_participants_added, false)
  assert.equal(state.membership_mode, 'project_groups')
  assert.deepEqual(state.infrastructure_group_ids, ['announcements@g.us'])
})

test('creates project groups inside the stored community', async (context) => {
  const root = await mkdtemp(path.join(os.tmpdir(), 'whatsapp-community-project-'))
  context.after(() => rm(root, { recursive: true, force: true }))
  const stateFile = path.join(root, 'community.json')
  const socket = {
    async communityCreate(subject) {
      return { id: 'community@g.us', isCommunity: true, subject }
    },
    async communityFetchLinkedGroups() {
      return { linkedGroups: [{ id: 'announcements@g.us' }] }
    },
    async groupMetadata(id) {
      return id === 'announcements@g.us'
        ? { id, isCommunityAnnounce: true, linkedParent: 'community@g.us' }
        : { id, isCommunity: true, subject: 'Nienfos' }
    },
    async communityCreateGroup(subject, participants, parentCommunityJid) {
      assert.equal(parentCommunityJid, 'community@g.us')
      assert.deepEqual(participants, ['bruno@s.whatsapp.net', 'mariano@s.whatsapp.net'])
      return { id: 'project@g.us', subject }
    },
  }
  const manager = new CommunityManager({ stateFile, subject: 'Nienfos' })
  const participants = ['bruno@s.whatsapp.net', 'mariano@s.whatsapp.net']
  await manager.ensureCommunity(socket, [], participants)
  const group = await manager.createProjectGroup(socket, {
    participants,
    subject: 'Nienfos · Proyecto',
  })
  assert.equal(group.id, 'project@g.us')
})

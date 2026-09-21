import assert from 'node:assert/strict'
import http from 'node:http'
import test from 'node:test'

import { ProjectFactoryClient } from '../src/project-factory-client.mjs'

async function testServer(t, handler) {
  const server = http.createServer(handler)
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve))
  t.after(() => new Promise((resolve) => server.close(resolve)))
  const address = server.address()
  return `http://127.0.0.1:${address.port}`
}

test('creates a guided Project Factory draft for a new WhatsApp group', async (t) => {
  let createdPayload = null
  const baseUrl = await testServer(t, async (request, response) => {
    if (request.method === 'GET') {
      response.setHeader('Content-Type', 'application/json')
      return response.end(JSON.stringify({ drafts: [] }))
    }
    let body = ''
    for await (const chunk of request) body += chunk
    createdPayload = JSON.parse(body)
    response.setHeader('Content-Type', 'application/json')
    response.end(JSON.stringify({ draft_id: 'pf-draft-new' }))
  })
  const client = new ProjectFactoryClient({ baseUrl })

  const result = await client.ensureDraftForGroup({
    groupId: '123@g.us',
    subject: 'Nienfos · Cliente Álamo',
  })

  assert.deepEqual(result, { created: true, draftId: 'pf-draft-new' })
  assert.equal(createdPayload.name, 'Cliente Álamo')
  assert.equal(createdPayload.slug, 'cliente-alamo')
  assert.equal(createdPayload.guidedIntakeEnabled, true)
  assert.match(createdPayload.primaryGoal, /\[whatsapp-group:123@g\.us\]/)
})

test('reuses a prior draft after a registry-write interruption', async (t) => {
  let postCount = 0
  const baseUrl = await testServer(t, (request, response) => {
    response.setHeader('Content-Type', 'application/json')
    if (request.method === 'POST') postCount += 1
    response.end(JSON.stringify({
      drafts: [{
        draft_id: 'pf-draft-existing',
        primary_goal: '[whatsapp-group:456@g.us] Proyecto provisional',
      }],
    }))
  })
  const client = new ProjectFactoryClient({ baseUrl })
  const result = await client.ensureDraftForGroup({ groupId: '456@g.us', subject: 'Cliente' })
  assert.deepEqual(result, { created: false, draftId: 'pf-draft-existing' })
  assert.equal(postCount, 0)
})

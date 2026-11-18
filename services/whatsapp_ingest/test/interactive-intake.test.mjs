import test from 'node:test'
import assert from 'node:assert/strict'
import { mkdtemp, mkdir, writeFile, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'
import { randomBytes, createHash, createHmac, createCipheriv } from 'node:crypto'
import { proto } from '@whiskeysockets/baileys'
import { InteractiveIntake } from '../src/interactive-intake.mjs'
import { IntakeStore } from '../src/store.mjs'
const recipient = '5491100000000@s.whatsapp.net'
const creator = '5491199999999@s.whatsapp.net'
function vote(poll, label, secret, voter = recipient) {
  const first = createHmac('sha256', Buffer.alloc(32)).update(secret).digest()
  const key = createHmac('sha256', first).update(Buffer.concat([
    Buffer.from(poll), Buffer.from(creator), Buffer.from(voter), Buffer.from('Poll Vote'), Buffer.from([1]),
  ])).digest()
  const encIv = randomBytes(12)
  const cipher = createCipheriv('aes-256-gcm', key, encIv)
  cipher.setAAD(Buffer.from(`${poll}\0${voter}`))
  const body = proto.Message.PollVoteMessage.encode({selectedOptions:[createHash('sha256').update(label).digest()]}).finish()
  return {key:{id:`vote-${poll}`,remoteJid:voter,fromMe:false},message:{pollUpdateMessage:{
    pollCreationMessageKey:{id:poll,fromMe:true},vote:{encIv,encPayload:Buffer.concat([cipher.update(body),cipher.final(),cipher.getAuthTag()])},
  }}}
}
test('native polls → selection → durable request → reply → continued chat; isolation and old votes', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(),'interactive-'))
  try {
    const root=path.join(dir,'interactive');await mkdir(root)
    await writeFile(path.join(root,'config.json'),JSON.stringify({enabled:true}))
    const projects=Array.from({length:20},(_,i)=>({slug:`project-${i}`,name:`Project ${i}`}))
    await writeFile(path.join(root,'catalog.json'),JSON.stringify({updated_at:Date.now()/1000,projects}))
    const flow=new InteractiveIntake({dataDir:dir,recipient,settleMs:0})
    const secrets=new Map(),sent=[]
    const socket={user:{id:creator},sendMessage:async(jid,content)=>{
      const id=`out-${sent.length}`;sent.push({jid,content,id});const secret=randomBytes(32);secrets.set(id,secret)
      return {key:{id},message:{messageContextInfo:{messageSecret:secret}}}
    }}
    const message={key:{id:'incoming',remoteJid:recipient,fromMe:false}}
    const store=new IntakeStore(dir);await store.initialize()
    const original=await store.persist({project:'direct-bruno',manifest:{message_id:'incoming',kind:'text',text:'Consulta'},ready:false})
    await assert.rejects(readFile(path.join(original.path,'READY')))
    await flow.capture(socket,message,original.path,'Consulta');await flow.tick(socket)
    assert.equal(sent[0].content.poll.values[1],'project-0')
    const first=sent[0]
    assert.equal(await flow.handleVote(socket,vote(first.id,'project-0',secrets.get(first.id),'other@s.whatsapp.net')),true)
    assert.equal(sent.length,1)
    await flow.handleVote(socket,vote(first.id,'Más proyectos →',secrets.get(first.id)))
    assert.ok(sent[1].content.poll.values.includes('project-5'))
    assert.ok(sent[1].content.poll.values.length<=12)
    const page=sent[1];await flow.handleVote(socket,vote(page.id,'project-5',secrets.get(page.id)))
    const channel=sent[2];assert.ok(channel.content.poll.values.includes('Bridge · Ejecutar'))
    await flow.handleVote(socket,vote(channel.id,'WhatsApp · Charlar',secrets.get(channel.id)))
    const state=JSON.parse(await readFile(flow.file,'utf8'))
    const file=path.join(root,'requests',`${state.id}.json`)
    const request=JSON.parse(await readFile(file,'utf8'))
    assert.equal(request.project,'project-5');assert.equal(request.channel,'whatsapp')
    assert.equal(request.records.length,1)
    const count=sent.length
    await flow.handleVote(socket,vote(channel.id,'Bridge · Ejecutar',secrets.get(channel.id)))
    assert.equal(sent.length,count)
    await writeFile(file,JSON.stringify({...request,status:'finished',session_id:'s',reply:'Respuesta real del adaptador de prueba'}))
    const restarted=new InteractiveIntake({dataDir:dir,recipient,settleMs:0})
    await restarted.tick(socket);await restarted.tick(socket)
    assert.equal(sent.filter(s=>s.content.text==='Respuesta real del adaptador de prueba').length,1)
    await restarted.capture(socket,{key:{id:'next',remoteJid:recipient},message:{extendedTextMessage:{text:'Otra consulta',contextInfo:{stanzaId:sent.find(s=>s.content.text==='Respuesta real del adaptador de prueba').id,participant:creator}}}},original.path,'Otra consulta')
    await restarted.tick(socket)
    const followup=JSON.parse(await readFile(flow.file,'utf8'))
    assert.equal(followup.session_id,'s');assert.equal(followup.project,'project-5')
    assert.equal(followup.phase,'submitted')
    const followFile=path.join(root,'requests',`${followup.id}.json`)
    const queued=JSON.parse(await readFile(followFile,'utf8'))
    await writeFile(followFile,JSON.stringify({...queued,status:'finished',channel:'bridge',session_id:'s',reply:'must-not-send'}))
    const beforeBridge=sent.length
    await restarted.tick(socket)
    assert.equal(sent.length,beforeBridge)
    await assert.rejects(restarted.capture(socket,{key:{id:'intruder',remoteJid:'other@s.whatsapp.net'}},original.path,'wrong'))
    assert.equal(await restarted.control(socket,{key:{remoteJid:'other@s.whatsapp.net'}},'nuevo'),false)
    assert.equal(await restarted.control(socket,message,'nuevo'),true)
    assert.equal(JSON.parse(await readFile(flow.file,'utf8')).reset_next,true)
  } finally {await rm(dir,{recursive:true,force:true})}
})


test('five projects per page preserves ordered catalog and navigation at boundaries', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'five-projects-'))
  try {
    const root = path.join(dir, 'interactive'); await mkdir(root)
    const projects = Array.from({length: 17}, (_, i) => ({slug: `project-${i}`}))
    await writeFile(path.join(root, 'catalog.json'), JSON.stringify({updated_at: Date.now()/1000, projects}))
    const flow = new InteractiveIntake({dataDir: dir, recipient})
    const sent = []
    const socket = {user: {id: creator}, sendMessage: async (jid, content) => {
      sent.push(content); return {key: {id: `page-${sent.length}`}, message: {messageContextInfo: {messageSecret: randomBytes(32)}}}
    }}
    const seen = []
    for (let page = 0; page < 4; page++) {
      await flow.advance(socket, {id: 'paging', polls: [], page})
      const values = sent.at(-1).poll.values
      const items = values.filter(v => v.startsWith('project-'))
      assert.deepEqual(items, projects.slice(page*5, (page+1)*5).map(p => p.slug))
      assert.ok(items.length <= 5)
      assert.ok(values.includes('CLI general')); assert.ok(values.includes('Cancelar'))
      assert.equal(values.includes('← Anteriores'), page > 0)
      assert.equal(values.includes('Más proyectos →'), page < 3)
      seen.push(...items)
    }
    assert.deepEqual(seen, projects.map(p => p.slug))
  } finally { await rm(dir, {recursive: true, force: true}) }
})

test('normal messages reset; quoted text/media recover older sessions after restart; pending selections survive', async () => {
  const dir = await mkdtemp(path.join(os.tmpdir(), 'reply-routing-'))
  try {
    const root = path.join(dir, 'interactive'); await mkdir(path.join(root, 'requests'), {recursive:true})
    await writeFile(path.join(root, 'config.json'), JSON.stringify({enabled:true}))
    await writeFile(path.join(root, 'catalog.json'), JSON.stringify({updated_at:Date.now()/1000,projects:[{slug:'old-project'},{slug:'recent-project'}]}))
    for (const [id, project, session] of [['old','old-project','old-session'],['recent','recent-project','recent-session']]) {
      await writeFile(path.join(root,'requests',`${id}.json`), JSON.stringify({id,status:'delivered',project,session_id:session,channel:'whatsapp',cli:false,delivery_ids:[`answer-${id}`]}))
    }
    await writeFile(path.join(root,'dialog.json'),JSON.stringify({id:'recent',phase:'done',project:'recent-project',channel:'whatsapp',session_id:'recent-session',seen:[]}))
    const sent=[]
    const socket={user:{id:creator,lid:'998877@lid'},sendMessage:async(jid,content)=>{
      sent.push(content);return {key:{id:`sent-${sent.length}`},message:{messageContextInfo:{messageSecret:randomBytes(32)}}}
    }}
    let flow=new InteractiveIntake({dataDir:dir,recipient,settleMs:0})
    const incoming=(id,content={conversation:'New request'})=>({key:{id,remoteJid:recipient},message:content})
    const load=async()=>JSON.parse(await readFile(flow.file,'utf8'))
    await flow.capture(socket,incoming('normal'),path.join(dir,'normal-record'),'New request')
    await flow.tick(socket)
    const normal=await load()
    assert.equal(normal.phase,'awaiting_vote');assert.equal(normal.project,null);assert.equal(normal.channel,null);assert.equal(normal.session_id,null)
    assert.deepEqual(normal.records,['normal-record'])
    assert.ok(sent.at(-1).poll.values.includes('old-project'))
    // Continue the older conversation while the new destination remains undecided.
    const quote=(type,participant=creator,stanzaId='answer-old')=>({[type]:{contextInfo:{stanzaId,participant}}})
    await flow.capture(socket,incoming('quoted',quote('extendedTextMessage')),path.join(dir,'quoted-record'),'Follow up')
    await flow.tick(socket)
    const continued=await load()
    assert.equal(continued.session_id,'old-session');assert.equal(continued.project,'old-project');assert.equal(continued.phase,'submitted')
    const queued=JSON.parse(await readFile(path.join(root,'requests',`${continued.id}.json`),'utf8'))
    assert.equal(queued.reply_to_request,'old');assert.deepEqual(queued.records,['quoted-record'])
    const pending=JSON.parse(await readFile(path.join(root,'dialogs',`${normal.id}.json`),'utf8'))
    assert.equal(pending.phase,'awaiting_vote');assert.deepEqual(pending.records,['normal-record'])
    // Old poll still selects its own pending request, without stealing the quoted session.
    const poll=pending.polls[0]
    await flow.handleVote(socket,vote(poll.id,'recent-project',Buffer.from(poll.secret,'base64')))
    const preserved=JSON.parse(await readFile(path.join(root,'dialogs',`${normal.id}.json`),'utf8'))
    assert.equal(preserved.project,'recent-project');assert.equal(preserved.session_id,null)
    assert.equal((await load()).id,continued.id)
    flow=new InteractiveIntake({dataDir:dir,recipient,settleMs:0})
    await flow.capture(socket,incoming('quoted',quote('extendedTextMessage')),path.join(dir,'quoted-record'),'Repeated')
    assert.equal((await load()).id,continued.id)
    for (const type of ['imageMessage','audioMessage','videoMessage','documentMessage']) {
      const content={ephemeralMessage:{message:quote(type,'998877@lid')}}
      await flow.capture(socket,incoming(type,content),path.join(dir,type),'')
      await flow.tick(socket)
      const media=await load()
      assert.equal(media.session_id,'old-session');assert.equal(media.project,'old-project')
      assert.deepEqual(media.records,[type])
    }
    for (const [id,content] of [['foreign',quote('extendedTextMessage','other@s.whatsapp.net')],['unknown',quote('extendedTextMessage',creator,'not-a-final-answer')]]) {
      // Force previous dialog submitted, then ensure unrelated quotes choose a new destination.
      await flow.capture(socket,incoming(id,content),path.join(dir,id),'New')
      await flow.tick(socket)
      const fresh=await load();assert.equal(fresh.session_id,null);assert.equal(fresh.project,null)
      assert.equal(fresh.phase,'awaiting_vote')
    }
    await assert.rejects(flow.capture(socket,{...incoming('attacker',quote('imageMessage')),key:{id:'attacker',remoteJid:'other@s.whatsapp.net'}},dir,''))
    // A plain message after an outstanding submitted job also starts afresh.
    await flow.capture(socket,incoming('resume',quote('extendedTextMessage')),dir,'More');await flow.tick(socket)
    await flow.capture(socket,incoming('fresh-after-submitted'),dir,'Unrelated')
    const fresh=await load();assert.equal(fresh.session_id,null);assert.equal(fresh.channel,null);assert.equal(fresh.project,null)
  } finally {await rm(dir,{recursive:true,force:true})}
})

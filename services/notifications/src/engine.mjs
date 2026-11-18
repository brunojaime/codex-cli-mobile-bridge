import {createHash} from 'node:crypto';
import {createNotifications,createFcmTransport,serviceAccountToken} from '@nienfos/notifications';
import {createD1Store} from '@nienfos/notifications/d1';
export const hash=value=>createHash('sha256').update(value).digest('hex');
export function createEngine({db,environment,projectId,origin,credential,bridgeId,fetcher,now=Date.now}) {
 const sql=db.connection,scope={appId:'codex-mobile',environment},store=createD1Store(db);
 const one=(query,...p)=>sql.prepare(query).get(...p);
 const eventFor=job=>one('SELECT * FROM bridge_push_events WHERE id=?',job.eventId);
 const active=p=>one('SELECT * FROM bridge_push_installations WHERE id=? AND enabled=1 AND updated_at>?',p.sessionId,now()-30*86400000);
 // A native background handler fetches the authorized text/logo from the bridge.
 // FCM receives only opaque references; high priority wakes Android to show it.
 const privateFetcher=async(url,options)=>{
  if(url.startsWith('https://fcm.googleapis.com/')) {
   const body=JSON.parse(options.body),m=body.message;
   if(m.android){delete m.notification;m.android={ttl:m.android.ttl,priority:'HIGH'};m.data={...m.data,bridgeId};}
   options={...options,body:JSON.stringify(body)};
  }
  return (fetcher??fetch)(url,options);
 };
 const transport=createFcmTransport({projectId,origin,accessToken:serviceAccountToken(credential,fetcher??fetch,now),fetcher:privateFetcher,now});
 function unread(event,installation) {
  if(!event||event.cancelled_at)return false;
  if(event.kind==='device.test')return event.installation_id===installation;
  const session=one('SELECT workspace_path,archived_at FROM sessions WHERE id=?',event.session_id);
  if(!session||session.archived_at)return false;
  const stamp=event.ready_at??event.created_at;
  return !one('SELECT 1 FROM bridge_push_reads WHERE installation_id=? AND resource IN (?,?) AND read_at>=?',installation,'chat:'+event.session_id,'project:'+session.workspace_path,stamp);
 }
 const notifications=createNotifications({scope,origin,store,enabled:true,clientMode:'native',now,
  authenticate:async request=>{
   const bearer=request.headers.get('authorization')?.slice(7)??'';
   const device=one('SELECT id FROM bridge_push_installations WHERE credential_hash=? AND enabled=1',hash(bearer));
   return device?{userId:'bridge-owner',tenantId:'bridge',sessionId:device.id}:null;
  },
  allowRegistration:async()=>true, // HTTP adapter applies the persistent limiter before RPC.
  canDeliver:async principal=>Boolean(active(principal)),
  canDeliverJob:async job=>{
   const event=eventFor(job),device=active(job);
   return Boolean(device&&(event?.kind==='device.test'||device.verified_at)&&unread(event,job.installationId));
  },deliver:transport
 });
 function projectBusy(workspace,event={}) {
  return Boolean(one(`SELECT 1 FROM sessions s WHERE s.workspace_path=? AND
   (s.active_agent_run_id IS NOT NULL OR EXISTS(SELECT 1 FROM jobs j WHERE j.session_id=s.id AND
   (j.status IN ('pending','running') OR (j.status IN ('completed','failed') AND j.auto_chain_processed=0 AND ((? IS NOT NULL AND j.run_id=?) OR j.id=?)))) OR
   EXISTS(SELECT 1 FROM messages m WHERE m.session_id=s.id AND m.role='assistant' AND m.status IN ('pending','reserved')))
   LIMIT 1`,workspace,event.run_id??null,event.run_id??null,event.job_id??null));
 }
 async function expand() {
  const events=sql.prepare('SELECT * FROM bridge_push_events WHERE expanded_at IS NULL AND cancelled_at IS NULL ORDER BY created_at LIMIT 30').all();
  for(const event of events){
   let title='Codex Mobile',body='Tenés una respuesta lista para leer.',readyAt=event.ready_at??event.created_at;
   if(event.kind==='device.test')body='Las notificaciones de este teléfono están funcionando.';
   else {
    const session=one('SELECT * FROM sessions WHERE id=?',event.session_id);
    if(!session||session.archived_at){sql.prepare('UPDATE bridge_push_events SET cancelled_at=? WHERE id=?').run(now(),event.id);continue;}
    if(projectBusy(session.workspace_path,event))continue;
    const message=event.run_id?one(`SELECT * FROM messages WHERE session_id=? AND run_id=? AND role='assistant'
      AND status IN ('completed','failed','cancelled') ORDER BY created_at DESC,rowid DESC LIMIT 1`,event.session_id,event.run_id):one('SELECT * FROM messages WHERE id=?',event.message_id);
    if(!message||message.status==='cancelled'){sql.prepare('UPDATE bridge_push_events SET cancelled_at=? WHERE id=?').run(now(),event.id);continue;}
    // Use the last reply's timestamp so reading an earlier stage doesn't hide the final one.
    const ready=Math.max(event.created_at,Date.parse(message.updated_at)||0);readyAt=ready;
    sql.prepare('UPDATE bridge_push_events SET message_id=?,job_id=?,ready_at=? WHERE id=?').run(message.id,message.job_id,ready,event.id);
   }
   const expiresAt=readyAt+86400000;
   if(expiresAt<=now()){sql.prepare('UPDATE bridge_push_events SET cancelled_at=? WHERE id=?').run(now(),event.id);continue;}
   // The app-owned event came from a SQL trigger in the business transaction.
   // The shared outbox deduplicates expansion after a crash before this marker.
   await notifications.enqueue({userId:'bridge-owner',tenantId:'bridge'},{eventId:event.id,title,body,path:'/notifications/events/'+event.id,expiresAt});
   sql.prepare('UPDATE bridge_push_events SET expanded_at=? WHERE id=?').run(now(),event.id);
  }
 }
 return {notifications,store,unread,projectBusy,async tick(){await expand();return notifications.drain();},
  async register({bearer,installationId,token,platform}){
   const response=await notifications.handle(new Request(origin+'/notifications/devices',{method:'POST',headers:{Authorization:'Bearer '+bearer,'Content-Type':'application/json'},body:JSON.stringify({installationId,token,platform})}));
   if(!response.ok)throw Error('registration_rejected_'+response.status);
   return {ok:true};
  },async prune(){await notifications.prune();sql.prepare('DELETE FROM bridge_push_events WHERE created_at<?').run(now()-90*86400000);sql.prepare('DELETE FROM bridge_push_limits WHERE window_at<?').run(now()-7*86400000);sql.prepare('DELETE FROM bridge_push_reads WHERE read_at<?').run(now()-90*86400000);sql.prepare('DELETE FROM bridge_push_installations WHERE updated_at<?').run(now()-30*86400000);}
 };
}

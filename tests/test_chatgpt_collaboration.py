from __future__ import annotations
import json
import subprocess
from pathlib import Path
import tempfile
import threading
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from services.chatgpt_collaboration.core import Conflict, GithubResult, Monitor, Store, fingerprint
from services.chatgpt_collaboration.server import build_server


class FakeBridge:
    def __init__(self, workspace):
        self.workspace, self.receipts, self.submits = str(workspace), {}, 0
        self.current = {'run_id': 'origin', 'is_active': False}
        self.lost_ack, self.job_status = False, 'completed'

    def session(self, ident):
        assert ident == 'bridge-session'
        return dict(id=ident, workspace_path=self.workspace, current_run=self.current, messages=[], archived_at=None)

    def resolve(self, thread):
        return 'bridge-session'

    def receipt(self, ident):
        if ident not in self.receipts:
            raise HTTPError('',404,'',{},None)
        return self.receipts[ident]

    def submit(self, ident, payload):
        assert payload['session_id'] == 'bridge-session'
        if ident not in self.receipts:
            self.submits += 1
            self.receipts[ident] = dict(state='accepted',job={'job_id':'job-one','run_id':'continued'})
            self.current = {'run_id':'continued','is_active':False}
        if self.lost_ack:
            self.lost_ack = False
            raise ConnectionError('Lost response after acceptance')
        return self.receipts[ident]

    def job(self, ident):
        return {'status':self.job_status,'session_id':'bridge-session','run_id':'continued'}


class FakeVerifier:
    def __init__(self):
        self.ready=False
        self.invalid=False
    def check(self, folder, branch):
        if self.invalid:
            raise ValueError('Artifact hash mismatch')
        if not self.ready:
            return {'status':'waiting'}
        verified=folder/'verified';verified.mkdir(exist_ok=True)
        (verified/'result.md').write_text('Proposal only, no executable instructions.\n')
        (verified/'result.json').write_text('{}')
        return dict(status='validated',result_commit='b'*40,producer='codex-export')


class CollaborationTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.workspace=self.root/'workspace';self.workspace.mkdir()
        self.runs=self.root/'requests';self.folder=self.runs/'round-one';self.folder.mkdir(parents=True)
        request=dict(schema='codex-chatgpt/request/v1',run_id='round-one',repository='example/repo',input_commit='a'*40)
        request['request_digest']=fingerprint(request)
        (self.folder/'request.json').write_text(json.dumps(request))
        self.bridge=FakeBridge(self.workspace);self.verifier=FakeVerifier()
        self.store=Store(self.root/'state')
        self.monitor=Monitor(self.store,self.bridge,self.verifier,5,self.runs)
        self.payload=dict(run_folder=str(self.folder),session_id='bridge-session',conversation_url='https://chatgpt.com/c/test-one',continuation='Read the result and report; do not implement.',timeout_seconds=60)

    def due(self):
        row=self.store.get('round-one');row['next_check']=0;self.store.save(row)
        return self.monitor.advance('round-one')

    def test_idle_poll_then_resume_same_chat_once(self):
        self.monitor.register(self.payload)
        self.assertEqual(self.due()['state'],'waiting');self.assertEqual(self.bridge.submits,0)
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'completed');self.assertEqual(self.bridge.submits,1)
        self.assertEqual(self.due()['state'],'completed');self.assertEqual(self.bridge.submits,1)
        self.assertTrue((self.workspace/'.codex-mobile-bridge/chatgpt/round-one/result.md').is_file())

    def test_registration_is_idempotent_and_retarget_rejected(self):
        a=self.monitor.register(self.payload);b=self.monitor.register(self.payload)
        self.assertEqual(a['submission_id'],b['submission_id'])
        with self.assertRaises(Conflict):self.monitor.register({**self.payload,'continuation':'Other scope'})

    def test_restart_keeps_waiting_request(self):
        self.monitor.register(self.payload)
        self.monitor=Monitor(Store(self.root/'state'),self.bridge,self.verifier,5,self.runs)
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'completed')
        self.assertEqual(self.bridge.submits,1)

    def test_lost_ack_reconciles_same_outbox_without_second_submission(self):
        self.monitor.register(self.payload);self.verifier.ready=True;self.bridge.lost_ack=True
        self.assertEqual(self.due()['state'],'waking')
        self.monitor=Monitor(Store(self.root/'state'),self.bridge,self.verifier,5,self.runs)
        self.assertEqual(self.due()['state'],'completed');self.assertEqual(self.bridge.submits,1)

    def test_active_origin_waits_without_starting_second_codex(self):
        self.bridge.current['is_active']=True
        self.monitor.register(self.payload);self.verifier.ready=True
        self.assertEqual(self.due()['state'],'validated');self.assertEqual(self.bridge.submits,0)
        self.bridge.current['is_active']=False
        self.assertEqual(self.due()['state'],'completed')

    def test_bridge_clears_current_run_after_completion(self):
        self.bridge.current['is_active']=True
        self.monitor.register(self.payload)
        original_session=self.bridge.session
        def real_session(ident):
            snapshot=original_session(ident)
            if not self.bridge.current.get('is_active'):
                snapshot['current_run']=None
                snapshot['recent_runs']=[dict(self.bridge.current)]
            return snapshot
        self.bridge.session=real_session
        self.bridge.current['is_active']=False
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'completed')
        self.assertEqual(self.bridge.submits,1)

    def test_completed_intervening_turn_is_detected(self):
        self.monitor.register(self.payload)
        self.bridge.session=lambda ident: dict(workspace_path=self.bridge.workspace,
            current_run=None,recent_runs=[dict(run_id='intervening',is_active=False)],messages=[])
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,0)

    def test_new_user_turn_needs_attention(self):
        self.monitor.register(self.payload);self.verifier.ready=True
        self.bridge.current={'run_id':'new-user-turn','is_active':False}
        self.assertEqual(self.due()['state'],'needs_attention');self.assertEqual(self.bridge.submits,0)

    def test_invalid_result_schedules_inspection_without_implementation(self):
        self.monitor.register(self.payload);self.verifier.invalid=True
        self.assertEqual(self.due()['state'],'recovery_waking');self.assertEqual(self.bridge.submits,0)
        prompt=self.store.get('round-one')['recovery_payload']['message']
        self.assertIn('Verificá la entrega',prompt)

    def test_timeout_and_cancel_never_send(self):
        self.monitor.register(self.payload)
        row=self.store.get('round-one');row['deadline']=time.time()-1;self.store.save(row)
        self.assertEqual(self.due()['state'],'recovery_waking');self.assertEqual(self.bridge.submits,0)
        with self.assertRaises(Conflict):self.monitor.cancel('round-one')
        # A new request cancelled before any durable handoff never wakes Codex.
        row=self.store.get('round-one');row.update(state='waiting',recovery_payload=None);self.store.save(row)
        self.monitor.cancel('round-one')
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'cancelled');self.assertEqual(self.bridge.submits,0)

    def test_request_path_outside_private_root_rejected(self):
        with self.assertRaisesRegex(ValueError,'folder'):
            self.monitor.register({**self.payload,'run_folder':str(self.workspace)})

    def test_context_tampering_rejected(self):
        data=json.loads((self.folder/'request.json').read_text());data['input_commit']='c'*40
        (self.folder/'request.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError,'digest'):self.monitor.register(self.payload)

    def test_parallel_ticks_do_not_duplicate_resume(self):
        self.monitor.register(self.payload);self.verifier.ready=True
        threads=[threading.Thread(target=self.due) for _ in range(4)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(self.bridge.submits,1)

    def test_running_continuation_is_monitored(self):
        self.monitor.register(self.payload);self.verifier.ready=True;self.bridge.job_status='running'
        self.assertEqual(self.due()['state'],'running')
        self.bridge.job_status='completed'
        self.assertEqual(self.due()['state'],'completed');self.assertEqual(self.bridge.submits,1)

    def test_next_round_can_start_before_old_continuation_is_acknowledged(self):
        self.monitor.register(self.payload);self.verifier.ready=True;self.bridge.job_status='running'
        self.assertEqual(self.due()['state'],'running')
        self.bridge.job_status='completed'
        self.bridge.current={'run_id':'next-round-callback','is_active':True}
        self.assertEqual(self.due()['state'],'completed')
        self.assertEqual(self.bridge.submits,1)

    def test_next_round_can_start_before_verified_recovery_closure(self):
        self.schedule_recovery();self.bridge.job_status='running';self.due()
        self.bridge.job_status='completed';self.verifier.ready=True
        self.bridge.current={'run_id':'next-round-callback','is_active':True}
        self.assertEqual(self.due()['state'],'completed')
        self.assertEqual(self.bridge.submits,1)

    def test_closure_rejects_wrong_completed_job_identity(self):
        self.monitor.register(self.payload);self.verifier.ready=True;self.bridge.job_status='running'
        self.assertEqual(self.due()['state'],'running')
        self.bridge.job=lambda ident: {'status':'completed','session_id':'other-session','run_id':'continued'}
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,1)

    def test_generation_report_cannot_rearm_after_an_intervening_user_turn(self):
        self.schedule_recovery();self.bridge.job_status='running';self.due()
        self.monitor.defer('round-one','job-one')
        self.bridge.job_status='completed'
        self.bridge.current={'run_id':'user-new-turn','is_active':False}
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,1)

    def schedule_recovery(self):
        self.monitor.register(self.payload)
        row=self.store.get('round-one');row['recovery_at']=0;self.store.save(row)
        self.assertEqual(self.due()['state'],'recovery_waking')

    def test_default_supervised_mode_and_mobile_status(self):
        row=self.monitor.register(self.payload)
        self.assertEqual(row['delivery_mode'],'supervised')
        self.due()
        status=self.workspace/'.codex-mobile-bridge/chatgpt/round-one/status.json'
        data=json.loads(status.read_text())
        self.assertEqual(data['state'],'waiting')
        self.assertNotIn('continuation',data)
        self.assertNotIn('recovery_payload',data)

    def test_github_mode_requires_repository_specific_real_write_probe(self):
        with self.assertRaisesRegex(ValueError,'write_probe'):
            self.monitor.register({**self.payload,'delivery_mode':'github'})
        # A successful delivery in another repository cannot certify this one.
        self.monitor.register(self.payload)
        probe=self.store.get('round-one');probe.update(id='probe',state='completed',
            repository='other/repo',producer='chatgpt',completed_at=time.time())
        self.store.insert(probe,'probe-signature')
        with self.assertRaisesRegex(ValueError,'repository/project'):
            self.monitor._check_write_probe('probe',dict(repository='example/repo'))
        probe.update(repository='example/repo',producer='codex-export');self.store.save(probe)
        with self.assertRaisesRegex(ValueError,'repository/project'):
            self.monitor._check_write_probe('probe',dict(repository='example/repo'))

    def test_valid_write_probe_is_rechecked_and_project_scoped(self):
        self.monitor.register(self.payload)
        probe=self.store.get('round-one');probe.update(id='probe',state='completed',
            producer='chatgpt',completed_at=time.time(),project_id='another-project')
        self.store.insert(probe,'probe-signature')
        with self.assertRaisesRegex(ValueError,'repository/project'):
            self.monitor._check_write_probe('probe',dict(repository='example/repo'))
        probe['project_id']=None;self.store.save(probe)
        self.verifier.check=lambda *args:dict(status='validated',producer='chatgpt')
        self.monitor._check_write_probe('probe',dict(repository='example/repo'))
        probe['completed_at']=time.time()-86401;self.store.save(probe)
        with self.assertRaisesRegex(ValueError,'recent'):
            self.monitor._check_write_probe('probe',dict(repository='example/repo'))

    def test_recovery_wakes_existing_chat_once_and_requires_verified_result(self):
        self.schedule_recovery()
        self.bridge.job_status='running'
        self.assertEqual(self.due()['state'],'recovery_running')
        self.assertEqual(self.bridge.submits,1)
        self.assertEqual(self.due()['state'],'recovery_running')
        self.bridge.job_status='completed'
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,1)

    def test_recovery_restart_and_lost_ack_use_identical_receipt(self):
        self.schedule_recovery();self.bridge.lost_ack=True
        self.assertEqual(self.due()['state'],'recovery_waking')
        self.monitor=Monitor(Store(self.root/'state'),self.bridge,self.verifier,5,self.runs)
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'completed')
        self.assertEqual(self.bridge.submits,1)
        self.assertEqual(self.due()['state'],'completed')

    def report_generation(self):
        self.bridge.job_status='running'
        self.assertEqual(self.due()['state'], 'recovery_running')
        row=self.store.get('round-one')
        self.monitor.defer('round-one', row['recovery_job_id'])
        self.bridge.job_status='completed'
        return self.due()

    def test_generation_wait_survives_restart_and_late_result_continues_once(self):
        self.schedule_recovery()
        row=self.report_generation()
        self.assertEqual(row['state'], 'waiting')
        self.assertGreater(row['recovery_at'], time.time()+290)
        self.monitor=Monitor(Store(self.root/'state'),self.bridge,self.verifier,5,self.runs)
        self.assertEqual(self.due()['state'], 'waiting')
        self.assertEqual(self.bridge.submits, 1)
        self.verifier.ready=True
        self.assertEqual(self.due()['state'], 'completed')
        self.assertEqual(self.bridge.submits, 2)
        self.assertEqual(self.due()['state'], 'completed')
        self.assertEqual(self.bridge.submits, 2)

    def test_generation_reinspection_has_new_durable_identity_and_finite_limit(self):
        self.schedule_recovery()
        first=self.store.get('round-one')['recovery_submission_id']
        self.report_generation()
        row=self.store.get('round-one');row['recovery_at']=0;self.store.save(row)
        self.assertEqual(self.due()['state'], 'recovery_waking')
        second=self.store.get('round-one')['recovery_submission_id']
        self.assertNotEqual(first,second)
        self.bridge.lost_ack=True;self.bridge.job_status='running'
        self.assertEqual(self.due()['state'], 'recovery_waking')
        self.monitor=Monitor(Store(self.root/'state'),self.bridge,self.verifier,5,self.runs)
        self.report_generation()
        self.assertEqual(self.bridge.submits, 2)
        row=self.store.get('round-one');row['recovery_at']=0;self.store.save(row)
        self.assertEqual(self.due()['state'], 'recovery_waking')
        self.bridge.job_status='running';self.due()
        with self.assertRaisesRegex(Conflict, 'limit'):
            self.monitor.defer('round-one', 'job-one')
        self.bridge.job_status='completed'
        self.assertEqual(self.due()['state'], 'needs_attention')
        self.assertEqual(self.bridge.submits, 3)

    def test_generation_report_rejects_wrong_job_finished_job_and_expired_wait(self):
        self.schedule_recovery();self.bridge.job_status='running';self.due()
        with self.assertRaises(Conflict): self.monitor.defer('round-one','old-job')
        self.bridge.job_status='completed'
        with self.assertRaises(Conflict): self.monitor.defer('round-one','job-one')
        self.bridge.job_status='running'
        row=self.store.get('round-one');row['recovery_wait_deadline']=time.time()+200;self.store.save(row)
        with self.assertRaisesRegex(Conflict,'limit'): self.monitor.defer('round-one','job-one')

    def test_generation_wait_rejects_changed_chat_and_invalid_result(self):
        self.schedule_recovery();self.report_generation()
        self.bridge.current={'run_id':'new-user-run','is_active':False}
        self.verifier.ready=True
        self.assertEqual(self.due()['state'], 'needs_attention')
        self.assertEqual(self.bridge.submits, 1)

    def test_invalid_delivery_after_generation_report_never_rearms(self):
        self.schedule_recovery();self.bridge.job_status='running';self.due()
        self.monitor.defer('round-one','job-one')
        self.bridge.job_status='completed';self.verifier.invalid=True
        self.assertEqual(self.due()['state'], 'needs_attention')
        self.assertEqual(self.bridge.submits, 1)

    def test_defer_api_requires_auth_and_returns_persistent_receipt(self):
        self.schedule_recovery();self.bridge.job_status='running';self.due()
        server=build_server(self.monitor,'test-token',0)
        threading.Thread(target=server.serve_forever,daemon=True).start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url='http://127.0.0.1:'+str(server.server_port)+'/tasks/round-one/defer'
        body=json.dumps({'job_id':'job-one'}).encode()
        with self.assertRaises(HTTPError) as exc: urlopen(Request(url,data=body))
        self.assertEqual(exc.exception.code,401)
        req=Request(url,data=body,headers={'Authorization':'Bearer test-token'})
        result=json.load(urlopen(req))
        self.assertEqual(result['generation_report_job_id'],'job-one')
        self.assertNotIn('recovery_payload',result)
        self.bridge.job_status='completed'
        self.assertEqual(self.due()['state'],'waiting')

    def test_recovery_is_blocked_if_user_advanced_conversation(self):
        self.schedule_recovery()
        self.bridge.current={'run_id':'user-new-run','is_active':False}
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,0)

    def test_recovery_waits_for_active_origin_and_survives_pending_restart(self):
        self.bridge.current['is_active']=True
        self.monitor.register(self.payload)
        row=self.store.get('round-one');row['recovery_at']=0;self.store.save(row)
        self.assertEqual(self.due()['state'],'recovery_pending')
        self.assertEqual(self.bridge.submits,0)
        self.monitor=Monitor(Store(self.root/'state'),self.bridge,self.verifier,5,self.runs)
        self.bridge.current['is_active']=False
        self.assertEqual(self.due()['state'],'recovery_waking')
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'completed')
        self.assertEqual(self.bridge.submits,1)

    def test_recovery_invalid_result_never_claims_completion(self):
        self.schedule_recovery();self.verifier.invalid=True
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,1)

    def test_reconcile_inspected_closure_verifies_result_without_waking_or_retargeting(self):
        self.schedule_recovery();self.due()
        row=self.store.get('round-one')
        self.assertEqual(row['state'],'needs_attention')
        self.verifier.ready=True
        self.bridge.current={'run_id':'later-user-turn','is_active':False}
        self.bridge.job=lambda ident: {'status':'completed','session_id':'bridge-session'}
        closed=self.monitor.reconcile('round-one','job-one')
        self.assertEqual(closed['state'],'completed')
        self.assertEqual(closed['closure_kind'],'operator_reconciled')
        self.assertEqual(closed['producer'],'codex-export')
        self.assertEqual(self.bridge.submits,1)
        self.monitor.reconcile('round-one','job-one')
        self.assertEqual(self.bridge.submits,1)

    def test_reconcile_rejects_missing_result_wrong_job_chat_and_unfinished_work(self):
        self.schedule_recovery();self.due()
        with self.assertRaises(Conflict):self.monitor.reconcile('round-one','other-job')
        self.bridge.job=lambda ident: {'status':'running','session_id':'bridge-session'}
        with self.assertRaises(Conflict):self.monitor.reconcile('round-one','job-one')
        self.bridge.job=lambda ident: {'status':'completed','session_id':'other-session'}
        with self.assertRaises(Conflict):self.monitor.reconcile('round-one','job-one')
        self.bridge.job=lambda ident: {'status':'completed','session_id':'bridge-session'}
        with self.assertRaises(Conflict):self.monitor.reconcile('round-one','job-one')
        self.assertEqual(self.store.get('round-one')['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,1)

    def test_recovery_uncertain_outbox_never_creates_second_submission(self):
        self.schedule_recovery()
        row=self.store.get('round-one')
        self.bridge.receipts[row['recovery_submission_id']]={'state':'uncertain'}
        self.assertEqual(self.due()['state'],'needs_attention')
        self.monitor.retry('round-one')
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,0)

    def test_parallel_recovery_ticks_submit_once(self):
        self.schedule_recovery();self.bridge.job_status='running'
        threads=[threading.Thread(target=self.due) for _ in range(4)]
        for thread in threads:thread.start()
        for thread in threads:thread.join()
        self.assertEqual(self.bridge.submits,1)

    def test_explicit_recover_does_not_retarget_or_duplicate(self):
        self.monitor.register(self.payload)
        row=self.store.get('round-one');row['state']='timed_out';self.store.save(row)
        first=self.monitor.recover('round-one')
        second=self.monitor.recover('round-one')
        self.assertEqual(first['recovery_submission_id'],second['recovery_submission_id'])
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'completed')
        with self.assertRaises(Conflict):self.monitor.recover('round-one')

    def test_bridge_outage_preserves_recovery_beyond_five_checks(self):
        self.schedule_recovery()
        receipt=self.bridge.receipt
        self.bridge.receipt=lambda ident: (_ for _ in ()).throw(ConnectionError())
        for _ in range(7):
            self.assertEqual(self.due()['state'],'recovery_waking')
        self.bridge.receipt=receipt;self.verifier.ready=True
        self.assertEqual(self.due()['state'],'completed')
        self.assertEqual(self.bridge.submits,1)

    def test_environment_change_blocks_recovery(self):
        self.monitor.bridge_environment='dev'
        self.bridge.url='http://127.0.0.1:8118'
        self.bridge.call=lambda path:{'environment_identity':{'environment':'dev'}}
        self.schedule_recovery()
        self.bridge.call=lambda path:{'environment_identity':{'environment':'prod'}}
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,0)

    def test_attention_notice_is_visible_once_and_does_not_resume_old_work(self):
        self.monitor.register(self.payload)
        row=self.store.get('round-one');row.update(state='needs_attention',problem='Conversation advanced');self.store.save(row)
        self.bridge.current={'run_id':'new-user-run','is_active':False}
        self.monitor.tick()
        notice=self.store.get('round-one')
        self.assertIsNotNone(notice.get('attention_job_id'))
        self.assertIn('No retomes el encargo antiguo',notice['attention_payload']['message'])
        self.monitor=Monitor(Store(self.root/'state'),self.bridge,self.verifier,5,self.runs)
        self.monitor.tick()
        self.assertEqual(self.bridge.submits,1)
        self.assertEqual(self.store.get('round-one')['state'],'needs_attention')

    def test_attention_waits_for_user_activity_and_environment(self):
        self.monitor.register(self.payload)
        row=self.store.get('round-one');row.update(state='needs_attention',problem='Unavailable');self.store.save(row)
        self.bridge.current['is_active']=True
        self.monitor.tick();self.assertEqual(self.bridge.submits,0)
        self.bridge.current['is_active']=False
        row=self.store.get('round-one');row['next_attention_check']=0;self.store.save(row)
        self.monitor.bridge_environment='dev'
        self.bridge.call=lambda path:{'environment_identity':{'environment':'prod'}}
        self.monitor.tick();self.assertEqual(self.bridge.submits,0)

    def test_legacy_terminal_tasks_are_not_reactivated_by_upgrade(self):
        self.monitor.register(self.payload)
        row=self.store.get('round-one');row.update(state='timed_out');row.pop('recovery_protocol');self.store.save(row)
        self.monitor.tick()
        self.assertEqual(self.bridge.submits,0)
        self.assertEqual(self.store.get('round-one')['state'],'timed_out')

    def test_notice_lost_ack_is_reconciled_without_duplicate(self):
        self.monitor.register(self.payload)
        row=self.store.get('round-one');row.update(state='needs_attention',problem='Blocked');self.store.save(row)
        self.bridge.lost_ack=True
        self.monitor.tick();self.assertEqual(self.bridge.submits,1)
        row=self.store.get('round-one');row['next_attention_check']=0;self.store.save(row)
        self.monitor=Monitor(Store(self.root/'state'),self.bridge,self.verifier,5,self.runs)
        self.monitor.tick()
        self.assertEqual(self.bridge.submits,1)
        self.assertIsNotNone(self.store.get('round-one').get('attention_delivered_at'))

    def test_api_recover_persists_and_redacts_prompts(self):
        self.monitor.register(self.payload)
        server=build_server(self.monitor,'test-token',0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url='http://127.0.0.1:'+str(server.server_port)
        health=json.load(urlopen(url+'/health'))
        self.assertEqual(health['recovery_protocol'],2)
        req=Request(url+'/tasks/round-one/recover',data=b'',method='POST',headers={'Authorization':'Bearer test-token'})
        first=json.load(urlopen(req));second=json.load(urlopen(req))
        self.assertEqual(first['state'],'recovery_waking')
        self.assertEqual(first['recovery_submission_id'],second['recovery_submission_id'])
        self.assertNotIn('recovery_payload',first)
        self.assertNotIn('continuation',first)

    def test_github_registration_reuses_receipt_after_probe_expires(self):
        probe=dict(id='probe',state='completed',repository='example/repo',producer='chatgpt',
                   completed_at=time.time(),private_folder=str(self.folder),branch='collaboration/probe',
                   next_check=0,updated_at=time.time())
        self.store.insert(probe,'probe-signature')
        self.verifier.check=lambda *args:dict(status='validated',producer='chatgpt')
        payload={**self.payload,'delivery_mode':'github','write_probe_run_id':'probe'}
        first=self.monitor.register(payload)
        probe['completed_at']=time.time()-86401;self.store.save(probe)
        self.assertEqual(self.monitor.register(payload)['submission_id'],first['submission_id'])

    def bind_project(self, include_request=True):
        registry=self.root/'.local/share/chatgpt-collaboration/projects.json'
        registry.parent.mkdir(parents=True)
        registry.write_text(json.dumps({'projects':[dict(id='product-one',
            repository='example/repo',repositories=['example/repo'],context_verified=True,
            chatgpt_project_url='https://chatgpt.com/g/g-p-123456/project')]}))
        if include_request:
            request=json.loads((self.folder/'request.json').read_text())
            request.update(project_id='product-one',chatgpt_project_id='g-p-123456')
            request['request_digest']=fingerprint({k:v for k,v in request.items() if k!='request_digest'})
            (self.folder/'request.json').write_text(json.dumps(request))
        context=patch('services.chatgpt_collaboration.core.Path.home',return_value=self.root)
        context.start();self.addCleanup(context.stop)

    def test_known_product_requires_explicit_project(self):
        self.bind_project(include_request=False)
        with self.assertRaisesRegex(ValueError,'requires --project'):
            self.monitor.register(self.payload)

    def test_general_chat_rejected_for_project_bound_request(self):
        self.bind_project()
        with self.assertRaisesRegex(ValueError,'must belong'):
            self.monitor.register(self.payload)

    def test_wrong_project_rejected(self):
        self.bind_project()
        with self.assertRaisesRegex(ValueError,'must belong'):
            self.monitor.register({**self.payload,'conversation_url':'https://chatgpt.com/g/g-p-other/c/test'})

    def test_correct_project_with_display_slug_accepted(self):
        self.bind_project()
        result=self.monitor.register({**self.payload,
            'conversation_url':'https://chatgpt.com/g/g-p-123456-my-product/c/test'})
        self.assertEqual(result['state'],'waiting')

    def test_dev_rejects_other_product_before_bridge_access(self):
        self.monitor.required_project='codex-cli-mobile-bridge'
        with self.assertRaisesRegex(ValueError,'restricted to project'):
            self.monitor.register(self.payload)

    def test_dev_rejects_other_repository(self):
        self.monitor.required_repository='brunojaime/codex-cli-mobile-bridge'
        with self.assertRaisesRegex(ValueError,'restricted to repository'):
            self.monitor.register(self.payload)

    def test_dev_rejects_prod_identity_even_on_configured_url(self):
        self.monitor.bridge_environment='dev'
        self.bridge.call=lambda path:{'environment_identity':{'environment':'prod'}}
        with self.assertRaisesRegex(ValueError,'environment identity'):
            self.monitor.register(self.payload)

    def test_identity_change_before_callback_never_submits(self):
        self.monitor.bridge_environment='dev'
        self.bridge.url='http://127.0.0.1:8118'
        self.bridge.call=lambda path:{'environment_identity':{'environment':'dev'}}
        self.monitor.register(self.payload)
        self.bridge.call=lambda path:{'environment_identity':{'environment':'prod'}}
        self.verifier.ready=True
        self.assertEqual(self.due()['state'],'needs_attention')
        self.assertEqual(self.bridge.submits,0)

    def test_api_auth_and_status(self):
        server=build_server(self.monitor,'test-token',0)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.addCleanup(server.server_close);self.addCleanup(server.shutdown)
        url='http://127.0.0.1:'+str(server.server_port)
        self.assertEqual(json.load(urlopen(url+'/health'))['status'],'ok')
        with self.assertRaises(HTTPError) as caught:urlopen(url+'/tasks')
        self.assertEqual(caught.exception.code,401)
        req=Request(url+'/tasks',json.dumps(self.payload).encode(),{'Authorization':'Bearer test-token','Content-Type':'application/json'})
        self.assertEqual(json.load(urlopen(req))['state'],'waiting')
        req=Request(url+'/tasks',headers={'Authorization':'Bearer test-token'})
        self.assertEqual(len(json.load(urlopen(req))),1)


class GithubTransportTest(unittest.TestCase):
    def test_external_api_timeout_uses_git_fallback(self):
        ready=SimpleNamespace(returncode=0,stdout=json.dumps({'status':'validated'}))
        with patch('services.chatgpt_collaboration.core.subprocess.run',
                   side_effect=[subprocess.TimeoutExpired('exchange',100),ready]) as run:
            self.assertEqual(GithubResult(Path('/skill')).check(Path('/run'),'collaboration/test')['status'],'validated')
            self.assertEqual(run.call_args.args[0][-1],'git')

    def test_api_child_timeout_uses_fallback_and_both_transport_failures_stay_transient(self):
        timeout=SimpleNamespace(returncode=2,stdout=json.dumps({'status':'needs_attention','reason':"Command '['gh', 'api']' timed out after 45 seconds"}))
        ready=SimpleNamespace(returncode=0,stdout=json.dumps({'status':'validated'}))
        with patch('services.chatgpt_collaboration.core.subprocess.run',side_effect=[timeout,ready]):
            self.assertEqual(GithubResult(Path('/skill')).check(Path('/run'),'collaboration/test')['status'],'validated')
        with patch('services.chatgpt_collaboration.core.subprocess.run',side_effect=[timeout,timeout]):
            with self.assertRaisesRegex(RuntimeError,'Temporary GitHub transport'):
                GithubResult(Path('/skill')).check(Path('/run'),'collaboration/test')

    def test_api_delivery_ignores_a_stale_git_cache(self):
        response=SimpleNamespace(returncode=0,stdout=json.dumps({'status':'validated','producer':'codex-export'}))
        with patch('services.chatgpt_collaboration.core.subprocess.run',return_value=response) as run:
            result=GithubResult(Path('/skill/exchange.py')).check(Path('/private/run'),'collaboration/test')
        self.assertEqual(result['status'],'validated')
        self.assertEqual(run.call_count,1)
        self.assertEqual(run.call_args.args[0][-1],'github-api')

    def test_api_transport_failure_can_fallback_but_invalid_manifest_cannot(self):
        error=SimpleNamespace(returncode=2,stdout=json.dumps({'status':'needs_attention','reason':'GitHub request failed; check gh authentication, permissions and connectivity'}))
        ready=SimpleNamespace(returncode=0,stdout=json.dumps({'status':'validated'}))
        with patch('services.chatgpt_collaboration.core.subprocess.run',side_effect=[error,ready]) as run:
            self.assertEqual(GithubResult(Path('/skill')).check(Path('/run'),'collaboration/test')['status'],'validated')
            self.assertEqual(run.call_args.args[0][-1],'git')
        invalid=SimpleNamespace(returncode=2,stdout=json.dumps({'status':'needs_attention','reason':'Artifact hash mismatch'}))
        with patch('services.chatgpt_collaboration.core.subprocess.run',return_value=invalid) as run:
            self.assertEqual(GithubResult(Path('/skill')).check(Path('/run'),'collaboration/test')['status'],'needs_attention')
            self.assertEqual(run.call_count,1)


if __name__=='__main__':unittest.main()

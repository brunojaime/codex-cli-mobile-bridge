"""Contract and measurement checks; no provider access and no real credentials."""
import copy
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

import lab
import configure


class LabTests(unittest.TestCase):
    def setUp(self):
        self.case=lab.load_cases(lab.HERE/'cases.json')['cases'][0]

    def test_expected_answer_is_not_sent(self):
        data=lab.payload(self.case)
        self.assertEqual(set(data),{'state','questions'})
        self.assertNotIn('expected',data)
        self.assertNotIn('critical_accept_label',data)

    def test_variants_preserve_labels_and_score_order(self):
        original=copy.deepcopy(self.case)
        transformed=lab.variant(self.case,'reversed')
        self.assertEqual(self.case,original)
        self.assertEqual(transformed['expected'],original['expected'])
        self.assertEqual(list(transformed['question']['criteria']),list(reversed(original['question']['criteria'])))
        score={'state':'a','question':{'type':'score','criteria':['a','b']}}
        self.assertEqual(lab.variant(score,'reversed'),score)

    def test_cloudflare_envelope_and_control_headers(self):
        with patch.dict(os.environ,{'CLOUDFLARE_ACCOUNT_ID':'a'*32,'CLOUDFLARE_API_TOKEN':'test-key'},clear=True):
            url,headers,body=lab.request_spec('cloudflare','typesafe/jev',lab.payload(self.case))
        self.assertEqual(body['model'],'typesafe/jev')
        self.assertIn('questions',body['input'])
        self.assertEqual(headers['cf-aig-skip-cache'],'true')
        self.assertEqual(headers['cf-aig-collect-log'],'false')
        self.assertTrue(url.endswith('/ai/run'))

    def test_openrouter_uses_decision_endpoint(self):
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key'},clear=True):
            url,_,body=lab.request_spec('openrouter','typesafe/jev-1.13',lab.payload(self.case))
        self.assertEqual(url,'https://openrouter.ai/api/v1/systemone')
        self.assertIn('questions',body)

    def test_missing_credentials_fail_before_network(self):
        with patch.dict(os.environ,{},clear=True),self.assertRaises(ValueError):
            lab.request_spec('openrouter','typesafe/jev-1.13',{})

    def test_env_loader_does_not_execute_shell(self):
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,{},clear=True):
            p=Path(tmp)/'env';p.write_text('OPENROUTER_API_KEY="$(do-not-run)"\nOTHER_KEY=ignored\n');p.chmod(0o600)
            lab.load_env(p)
            self.assertEqual(os.environ['OPENROUTER_API_KEY'],'$(do-not-run)')
            self.assertNotIn('OTHER_KEY',os.environ)
            p.chmod(0o644)
            with self.assertRaises(ValueError):lab.load_env(p)

    def test_unknown_label_and_invalid_probability_fail(self):
        result=lab.baseline(self.case)
        result['answers']['decision']['choice']='not-a-label'
        with self.assertRaises(lab.RemoteFailure):lab.normalize(result,self.case['question'])
        result=lab.baseline(self.case)
        result['answers']['decision']['probabilities']['missing']=float('nan')
        with self.assertRaises(lab.RemoteFailure):lab.normalize(result,self.case['question'])

    def test_invalid_noul_and_score_fail(self):
        for typ,value,key in [('noul',1.1,'noul'),('score',-1,'score')]:
            with self.assertRaises(lab.RemoteFailure):
                lab.normalize({'answers':{'decision':{'type':typ,key:value}}},{'type':typ,'criteria':['a','b']})

    def test_auth_error_never_saves_provider_body(self):
        error=urllib.error.HTTPError('https://example.invalid',401,'Unauthorized',{},io.BytesIO(b'{"errors":[{"code":10000,"message":"echo-secret-test"}]}'))
        with patch.dict(os.environ,{'OPENROUTER_API_KEY':'test-key'},clear=True),patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=error
            with self.assertRaises(lab.RemoteFailure) as raised:
                lab.remote_call('openrouter','typesafe/jev-1.13',{},1)
        self.assertEqual(raised.exception.record['http_status'],401)
        self.assertNotIn('echo-secret-test',json.dumps(raised.exception.record))
        self.assertEqual(opener.return_value.open.call_count,1)

    def test_redirects_are_not_followed(self):
        self.assertIsNone(lab.NoRedirect().redirect_request(None,None,302,'',{},'https://example.invalid'))

    def test_metrics_do_not_count_variants_as_new_cases(self):
        a={'id':'a','family':'closure','expected':'missing','predicted':'supported','correct':False,
           'variant':'original','repeat':0,'critical_accept_label':'supported','latency_ms':2,'usage':{}}
        b={**a,'variant':'reversed','predicted':'missing','correct':True}
        m=lab.summarize([a,b])
        self.assertEqual(m['families']['closure']['cases'],1)
        self.assertEqual(m['families']['closure']['false_accepts'],1)
        self.assertEqual(m['robustness']['reversed']['changed'],1)
        self.assertIsNone(m['reported_cost_usd'])

    def test_empty_failures_do_not_become_accuracy(self):
        m=lab.summarize([{'error':{'http_status':401}}])
        self.assertEqual(m['valid_responses'],0)
        self.assertEqual(m['families'],{})

    def test_configurator_writes_private_file_without_echoing_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'private'/'credentials.env'
            output=io.StringIO()
            with patch('sys.argv',['configure.py','openrouter','--path',str(target)]),patch('getpass.getpass',return_value='fake-test-key'),patch('sys.stdout',output):
                configure.main()
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertIn('OPENROUTER_API_KEY=fake-test-key',target.read_text())
            self.assertNotIn('fake-test-key',output.getvalue())

    def test_configurator_invalid_input_preserves_previous_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'credentials.env'
            target.write_text('OPENROUTER_API_KEY=existing-test-value\n');target.chmod(0o600)
            with patch('sys.argv',['configure.py','openrouter','--path',str(target)]),patch('getpass.getpass',return_value='invalid value'),self.assertRaises(SystemExit):
                configure.main()
            self.assertEqual(target.read_text(),'OPENROUTER_API_KEY=existing-test-value\n')

if __name__=='__main__':unittest.main()

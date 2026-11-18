import json
import time

import httpx
import pytest

from scripts.project_work import nienfos_web_delivery as operator


def test_explicit_credential_file_is_used_without_exposing_other_values(tmp_path):
    path = tmp_path / 'credentials.env'
    path.write_text('CLOUDFLARE_API_TOKEN=FAKE_OPERATOR_TEST_TOKEN\nOTHER_PRIVATE_VALUE=FAKE_NOT_USED\n')
    env = operator.configured_environment({'credential_file': str(path)}, {'PATH': '/usr/bin'})
    assert env == {'PATH': '/usr/bin', 'CLOUDFLARE_API_TOKEN': 'FAKE_OPERATOR_TEST_TOKEN'}
    assert operator.configured_environment({}, env) == {'PATH': '/usr/bin'}


def test_missing_credential_fails_without_including_credential_file_contents(tmp_path):
    path = tmp_path / 'credentials.env'
    path.write_text('OTHER_PRIVATE_VALUE=FAKE_NOT_USED\n')
    with pytest.raises(RuntimeError, match='credential is unavailable') as exc:
        operator.configured_environment({'credential_file': str(path)}, {})
    assert 'FAKE_NOT_USED' not in str(exc.value)


@pytest.mark.parametrize('change', ['candidate', 'expiry', 'provider', 'page', None])
def test_reconciliation_rejects_every_changed_baseline(monkeypatch, change):
    revision = 'a' * 40
    provider = {'worker_version': 'live', 'modules': {'worker.js': 'digest'}, 'preserved_settings_sha256': 'settings'}
    baseline = {'candidate_commit': revision, 'expires_at': time.time()+300,
                'provider': provider, 'page_sha256': operator.sha(b'actual public page')}
    if change == 'candidate': baseline['candidate_commit'] = 'b'*40
    if change == 'expiry': baseline['expires_at'] = 0
    monkeypatch.setattr(operator, 'provider_snapshot', lambda *_: {} if change == 'provider' else provider)
    monkeypatch.setattr(operator.httpx, 'get', lambda *a, **kw: httpx.Response(200, content=b'changed' if change == 'page' else b'actual public page'))
    cfg = {'reconciled_baseline': baseline, 'origin': 'https://dev.example.invalid'}
    if change:
        with pytest.raises(AssertionError): operator.assert_reconciled_baseline(cfg, {}, revision)
    else:
        operator.assert_reconciled_baseline(cfg, {}, revision)

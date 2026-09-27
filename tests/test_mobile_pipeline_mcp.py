import json
from pathlib import Path
import pytest
from mcp_apps.mobile_pipeline import server

def enrolled(tmp_path):
    path=tmp_path/'gestion'/'infra/mobile';path.mkdir(parents=True)
    (path/'project.json').write_text(json.dumps({'kind':'nienfos.mobile-project','sourceApp':'gestion'}))
    (path/'release.json').write_text(json.dumps({'profile':'preview','version':'0.1.0','androidBuild':1,'toolkitVersion':'0.1.0'}))
    return path.parents[1]

def test_discovery_reports_pinned_consumer_without_secrets(tmp_path,monkeypatch):
    enrolled(tmp_path);monkeypatch.setattr(server,'ROOT',tmp_path)
    result=server.list_mobile_projects()
    assert result['projects'][0]['sourceApp']=='gestion'
    assert result['projects'][0]['toolkitUpdateAvailable'] is False
    assert 'password' not in json.dumps(result)

@pytest.mark.parametrize('name', ['../gestion', '/tmp/gestion', 'gestion;touch', 'gestion/../../x'])
def test_project_traversal_is_rejected(name,tmp_path,monkeypatch):
    monkeypatch.setattr(server,'ROOT',tmp_path)
    with pytest.raises(ValueError):server._project(name)

def test_symlink_escape_is_rejected(tmp_path,monkeypatch):
    outside=tmp_path/'outside';outside.mkdir();root=tmp_path/'projects';root.mkdir();(root/'gestion').symlink_to(outside,target_is_directory=True)
    monkeypatch.setattr(server,'ROOT',root)
    with pytest.raises(ValueError):server._project('gestion')

def test_publish_needs_human_reference_before_process(tmp_path,monkeypatch):
    enrolled(tmp_path);monkeypatch.setattr(server,'ROOT',tmp_path)
    with pytest.raises(ValueError):server.start_mobile_job('gestion','publish')

def test_arbitrary_operations_rejected(tmp_path,monkeypatch):
    enrolled(tmp_path);monkeypatch.setattr(server,'ROOT',tmp_path)
    with pytest.raises(ValueError):server.start_mobile_job('gestion','shell')

def test_sdk_update_preserves_unreviewed_custom_code(tmp_path,monkeypatch):
    root=enrolled(tmp_path);monkeypatch.setattr(server,'ROOT',tmp_path)
    target=root/'packages/mobile-core/index.ts';target.parent.mkdir(parents=True);target.write_text('custom code')
    with pytest.raises(ValueError):server.update_mobile_sdk('gestion')
    assert target.read_text()=='custom code'

def test_sdk_update_records_digest_and_requires_native_rebuild(tmp_path,monkeypatch):
    root=enrolled(tmp_path);monkeypatch.setattr(server,'ROOT',tmp_path)
    result=server.update_mobile_sdk('gestion')
    assert result['state']=='local-changes'
    assert 'authorized-publication' in result['requires']
    assert server.mobile_sdk_plan('gestion')['updateAvailable'] is False

def test_version_bump_monotonic_and_never_publishes(tmp_path,monkeypatch):
    enrolled(tmp_path);monkeypatch.setattr(server,'ROOT',tmp_path)
    result=server.bump_mobile_version('gestion','0.1.1')
    assert result['version']=='0.1.1' and result['build']==2
    with pytest.raises(ValueError):server.bump_mobile_version('gestion','0.0.9')

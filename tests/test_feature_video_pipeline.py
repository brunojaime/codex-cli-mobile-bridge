from pathlib import Path
import importlib.util
import json
import subprocess
import sys
import pytest

from backend.app.domain.video_handoff import VIDEO_HANDOFF_HINT,with_video_handoff
from backend.app.domain.entities.codex_options import CodexRunOptions
from backend.app.infrastructure.codex_tooling import discover_codex_skills
from backend.app.infrastructure.execution.local_provider import LocalExecutionProvider,_app_server_input_items
from backend.app.application.services.dev_pipeline_service import DevPipelineService

ROOT=Path(__file__).resolve().parents[1]
FILE=ROOT/'scripts/local_video/project.py'
spec=importlib.util.spec_from_file_location('project_video',FILE)
project=importlib.util.module_from_spec(spec);spec.loader.exec_module(project)


def test_cross_project_discovery(tmp_path):
    for name in ['project-a','project-b']:
        workspace=tmp_path/name;workspace.mkdir()
        skills=discover_codex_skills(Path.home(),repo_root=workspace)
        skill=next(x for x in skills if x.skill_id=='local-feature-videos')
        assert Path(skill.path).is_file()
        items=_app_server_input_items('Hacé un video de la función',CodexRunOptions(skill_ids=('local-feature-videos',)),str(workspace))
        assert items[1]['type']=='skill' and Path(items[1]['path']).is_file()
        assert not list(workspace.iterdir())


def test_optional_video_handoff(tmp_path,monkeypatch):
    # Prompt preparation itself performs no project mutation or execution.
    for message in ['Implementá filtros','Implementá filtros y hacé un video','No quiero video']:
        items=_app_server_input_items(message,None,str(tmp_path))
        assert len(items)==1 and items[0]['text'].count(VIDEO_HANDOFF_HINT)==1
        assert message in items[0]['text']
    provider=LocalExecutionProvider(command='codex',workdir=str(tmp_path))
    _,path,prompt=provider._build_command('Hacé un video')
    try:assert prompt.count(VIDEO_HANDOFF_HINT)==1
    finally:
        if path:Path(path).unlink(missing_ok=True)
    service=object.__new__(DevPipelineService)
    stage={'stage_id':'stage-a','status':'active','spec_id':'spec-a','worktree_path':str(tmp_path),'branch':'dev/a'}
    state={'sessions':{'s':{'stage_id':'stage-a'}},'runs':{},'backlog':{},'handoffs':{}}
    monkeypatch.setattr(service,'_require_enabled',lambda:None)
    monkeypatch.setattr(service,'_require_environment',lambda x:None)
    monkeypatch.setattr(service,'_read_state',lambda:state)
    monkeypatch.setattr(service,'_require_stage',lambda s,i:stage)
    monkeypatch.setattr(service,'validate_stage_session_execution',lambda **kw:None)
    service._quality_service=None
    for custom in [None,'Implementá X y después hacé video']:
        result=service.prepare_stage_run_start(stage_id='stage-a',session_id='s',backend_url='test',initial_prompt=custom)
        assert result['prompt'].count(VIDEO_HANDOFF_HINT)==1
        wrapped=_app_server_input_items(result['prompt'],None,str(tmp_path))[0]['text']
        assert wrapped.count(VIDEO_HANDOFF_HINT)==1
        if custom:assert custom in wrapped
    assert not list(tmp_path.iterdir())
    assert len(VIDEO_HANDOFF_HINT)<1100
    assert with_video_handoff(with_video_handoff('x'))==with_video_handoff('x')


def test_project_video_request(tmp_path):
    projects=[tmp_path/'a',tmp_path/'b']
    for workspace in projects:
        workspace.mkdir()
        cmd=[sys.executable,str(FILE),'--workspace',str(workspace),'--feature-id','upload','--feature','Carga de documentos','--request-ref','test:explicit']
        first=json.loads(subprocess.check_output(cmd,text=True));path=Path(first['path']);before=path.read_bytes()
        second=json.loads(subprocess.check_output(cmd,text=True))
        assert first['created'] and not second['created'] and before==path.read_bytes()
        assert first['request']['workspace']==str(workspace)
        assert first['request']['status']=='awaiting_feature_validation'
        assert first['request']['recipe'] is None and not first['request']['render_started']
        assert not (workspace/'reports').exists()
    assert (projects[0]/'.local-videos/upload/request.json').read_bytes()!=(projects[1]/'.local-videos/upload/request.json').read_bytes()
    with pytest.raises(ValueError):project.prepare(projects[0],'../escape','X','test:explicit')
    with pytest.raises(ValueError):project.prepare(projects[0],'upload','Otra función','test:explicit')
    (projects[0]/'.local-videos/link').symlink_to(projects[1],target_is_directory=True)
    with pytest.raises(ValueError):project.prepare(projects[0],'link','X','test:explicit')
    folder=projects[0]/'.local-videos/file-link';folder.mkdir()
    (folder/'request.json').symlink_to(projects[1]/'.local-videos/upload/request.json')
    with pytest.raises(ValueError):project.prepare(projects[0],'file-link','X','test:explicit')


def test_approved_video_defaults(tmp_path):
    normal=project.prepare(tmp_path,'default','Función','test:explicit',feature_ready=True)['request']
    assert normal['voice']=='voz-1' and normal['music']['mode']=='light-keys'
    assert normal['music']['level_db_below_voice']==18 and normal['music']['duck_db']==4
    assert normal['max_duration_seconds']==60 and normal['blockers']==[]
    assert normal['status']=='awaiting_recipe' and normal['recipe'] is None
    fast=project.prepare(tmp_path,'fast','Función','test:explicit-fast',fast=True)['request']
    assert fast['voice']=='peter-fast' and fast['fast_explicit']
    missing=project.prepare(tmp_path,'missing','Función','test:explicit',engine=tmp_path/'missing-engine',python=tmp_path/'missing-python')['request']
    assert missing['status']=='blocked_resources' and missing['blockers'] and not missing['render_started']


def test_reusable_pipeline_skill(tmp_path):
    source=ROOT/'scripts/local_video/skill/local-feature-videos';installed=Path.home()/'.codex/skills/local-feature-videos'
    for name in ['SKILL.md','pipeline.md','music.md','default-music-plan.json']:
        assert (source/name).read_bytes()==(installed/name).read_bytes()
    subprocess.run([sys.executable,str(Path.home()/'.codex/skills/.system/skill-creator/scripts/quick_validate.py'),str(installed)],check=True,capture_output=True)
    for name in ['one','two']:
        workspace=tmp_path/name;workspace.mkdir()
        result=project.prepare(workspace,'feature','Nueva función','test:explicit')
        record=Path(result['path']);data=json.loads(record.read_text());data.update(status='blocked',blockers=['recipe not implemented']);record.write_text(json.dumps(data))
        again=project.prepare(workspace,'feature','Nueva función','test:explicit')['request']
        assert again['status']=='blocked' and again['blockers']==['recipe not implemented']
        assert Path(again['engine'])==FILE.parent

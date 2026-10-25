"""Execute local integration checks and expose criterion-specific observations."""
from pathlib import Path
import json,os,subprocess,sys,tempfile,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
checks={
 'cross-project-discovery':'test_cross_project_discovery',
 'optional-video-handoff':'test_optional_video_handoff',
 'project-video-request':'test_project_video_request',
 'approved-video-defaults':'test_approved_video_defaults',
 'reusable-pipeline-skill':'test_reusable_pipeline_skill',
}
facts={}
with tempfile.TemporaryDirectory(prefix='video-pipeline-check-') as temp:
 xml=Path(temp)/'results.xml'
 command=[str(ROOT/'.venv/bin/python'),'-m','pytest','tests/test_feature_video_pipeline.py','tests/test_local_provider_skill_input.py','tests/test_local_provider_app_server.py',
 'tests/test_dev_pipeline.py::test_stage_run_uses_reviewer_auto_chain_preset_and_records_evidence',
 'tests/test_dev_pipeline.py::test_stage_run_start_guards_binding_branch_and_stage_status',
 'tests/test_message_flow.py::test_exec_command_reads_prompt_from_stdin_instead_of_argv',
 'tests/test_message_flow.py::test_exec_resume_command_reads_prompt_from_stdin_instead_of_argv',
 'tests/test_message_flow.py::test_app_server_streaming_exposes_partial_response_before_completion',
 '-q',f'--junitxml={xml}']
 env={**os.environ,'PIPELINE_QUALITY_DATABASE':str(Path(temp)/'quality.sqlite3')}
 result=subprocess.run(command,cwd=ROOT,capture_output=True,text=True,timeout=180,env=env)
 print(result.stdout);print(result.stderr)
 if xml.exists():
  cases=list(ET.parse(xml).iter('testcase'))
  passed={x.get('name') for x in cases if not any(x.find(t) is not None for t in ['failure','error','skipped'])}
  facts={key:name in passed for key,name in checks.items()}
  facts['pipeline-evidence']=result.returncode==0 and all(facts.values()) and len(cases)>=14
  print(json.dumps({'tests':len(cases),'passed':len(passed),'prompt_characters':len(__import__('backend.app.domain.video_handoff',fromlist=['VIDEO_HANDOFF_HINT']).VIDEO_HANDOFF_HINT),'scope':'local integration, no deployment or model run','target':'Bridge local source and installed shared skill'}))
 print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':facts}))
 sys.exit(result.returncode or (0 if facts and all(facts.values()) else 1))

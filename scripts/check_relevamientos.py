#!/usr/bin/env python3
"""Execute synthetic integration checks, never infer live evidence from them."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'reports/relevamientos-20261016'

def main():
    OUT.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory() as temp:
        junit=Path(temp)/'results.xml'
        result=subprocess.run([sys.executable,'-m','pytest','tests/test_relevamientos.py','-q',f'--junitxml={junit}'],cwd=ROOT,capture_output=True,text=True,timeout=120)
        (OUT/'tests.txt').write_text(result.stdout+result.stderr)
        cases=ET.parse(junit).findall('.//testcase') if junit.exists() else []
        outcomes={c.attrib['name']:not any(c.find(tag) is not None for tag in ('error','failure','skipped')) for c in cases}
        groups={
          'monitor-local':['test_discovery_upload_stability_duplicates_and_outputs','test_unavailable_download_never_queued','test_requested_folder_isolated_idempotent_and_incremental','test_requested_folder_rejects_ambiguity_and_missing_reference'],
          'recovery-local':['test_diarization_failure_resume_restart_without_asr','test_restart_from_inflight_stage','test_checksum_download_failure','test_drive_download_source_revision_changed'],
          'speakers-local':['test_speaker_correction_without_retranscription'],
          'analysis-local':['test_validation_rejects_hallucinated_trace','test_analysis_tools_disabled_and_bounded'],
          'consolidation-local':['test_new_meeting_consolidation','test_drive_pagination_scope_and_conflict'],
          'sync-local':['test_sync_retry_does_not_repeat_models','test_drive_atomic_upload_repeat_and_conditional_update'],
          'operations-local':['test_lock_and_force_archive'],
        }
        observations={key:all(outcomes.get(name,False) for name in names) for key,names in groups.items()}
        observations['tests-local']=len(cases)>=16 and result.returncode==0
        (OUT/'executed.json').write_text(json.dumps({'scope':'local synthetic adapters; not deployed acceptance','tests':outcomes,'observations':observations},indent=2)+'\n')
        print('NIENFOS_OBSERVATIONS_V1 '+json.dumps({'observations':observations}))
        return result.returncode
if __name__=='__main__':raise SystemExit(main())

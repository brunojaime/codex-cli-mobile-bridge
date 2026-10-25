#!/usr/bin/env python3
"""Execute offline WhatsApp video acceptance checks; never connects to WhatsApp."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/whatsapp-videos-20261005'


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    results = {}
    observations = {}
    node = os.environ.get('VIDEO_CHECK_NODE', str(Path.home() / '.nvm/versions/node/v22.22.2/bin/node'))
    flutter = os.environ.get('VIDEO_CHECK_FLUTTER', str(ROOT.parent / 'flutter/bin/flutter'))
    def run(name, argv, cwd=ROOT, env=None):
        log = OUT / f'{name}.txt'
        with log.open('w') as output:
            try:
                completed = subprocess.run(argv, cwd=cwd, env=env, stdout=output, stderr=subprocess.STDOUT, timeout=180)
                code = completed.returncode
            except subprocess.TimeoutExpired:
                code = 124
                output.write('\nCheck exceeded 180 seconds.\n')
        result = subprocess.CompletedProcess(argv, code, stdout=log.read_text())
        results[name] = {'exit_code': result.returncode}
        return result

    intake = run('intake', [node, '--test', *map(str, sorted((ROOT / 'services/whatsapp_ingest/test').glob('*.test.mjs')))])
    # Node reports every executed test, and exits nonzero for failure.
    node_count = next((int(line.split()[-1]) for line in intake.stdout.splitlines() if line.startswith('# tests ')), 0)
    results['intake']['tests'] = node_count
    observations['video-intake'] = intake.returncode == 0 and node_count >= 6
    with tempfile.TemporaryDirectory() as temp:
        junit = Path(temp) / 'tests.xml'
        backend = run('backend', [sys.executable, '-m', 'pytest',
            'tests/test_whatsapp_video.py', 'tests/test_whatsapp_intake_worker.py',
            'tests/test_message_flow.py::test_attachment_batch_flow_accepts_images',
            'tests/test_message_flow.py::test_attachment_batch_flow_accepts_video_reference',
            'tests/test_message_flow.py::test_attachment_batch_flow_treats_mislabeled_mp4_as_video',
            'tests/test_message_flow.py::test_attachment_batch_flow_accepts_standard_documents',
            'tests/test_message_flow.py::test_image_attachment_download_serves_persisted_file',
            'tests/test_message_flow.py::test_image_attachment_download_returns_404_for_invalid_index',
            'tests/test_message_flow.py::test_image_attachment_download_rejects_path_outside_retry_asset_root',
            'tests/test_message_flow.py::test_image_attachment_download_returns_404_for_missing_file',
            '-v', '--disable-warnings', f'--junitxml={junit}'], env={
                **os.environ, 'PIPELINE_QUALITY_DATABASE': str(Path(temp) / 'quality.sqlite3'),
                'PIPELINE_QUALITY_JEV_ENABLED': 'false',
            })
        cases = ET.parse(junit).findall('.//testcase') if junit.exists() else []
        def passed(case):
            return all(case.find(tag) is None for tag in ('error', 'failure', 'skipped'))
        video_cases = [c for c in cases if c.attrib['name'].startswith('test_video_')]
        e2e = [c for c in video_cases if c.attrib['name'].startswith('test_video_end_to_end[')]
        results['backend'].update(tests=len(cases), passed=sum(passed(c) for c in cases),
                                  video_cases=len(video_cases), end_to_end=len(e2e))
        observations['video-routing'] = len(video_cases) == 12 and all(passed(c) for c in video_cases)
        bridge_ok = len(e2e) == 8 and all(passed(c) for c in e2e)
    ui = run('mobile', [flutter, 'test', '--no-pub', '--reporter', 'expanded',
        'test/whatsapp_video_attachment_test.dart'], ROOT / 'frontend/mobile_app')
    ui_ok = ui.returncode == 0 and 'All tests passed!' in ui.stdout
    observations['video-bridge'] = bridge_ok and ui_ok
    observations['regressions-evidence'] = (
        intake.returncode == backend.returncode == 0 and ui_ok
        and len(cases) > len(video_cases) and all(passed(c) for c in cases)
    )
    evidence = {'target': 'local/offline integration; no deployed verification',
        'results': results, 'observations': observations,
        'boundaries': ['WhatsApp download is simulated with a real MP4 fixture',
            'Codex is a test process; no model API', 'No live service restarted or message sent',
            'Mobile widget action tested; no human visual inspection claimed']}
    (OUT / 'check-evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(evidence))
    print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps({'observations': observations}))
    return 0 if all(observations.values()) else 1


if __name__ == '__main__':
    raise SystemExit(main())

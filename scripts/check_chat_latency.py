#!/usr/bin/env python3
"""Run controlled client latency/regression tests; never sends production messages."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/chat-latency-20261009'


def main():
    files = ['chat_controller_latency_test.dart', 'chat_transcript_lazy_loading_test.dart',
             'chat_controller_streaming_response_test.dart', 'chat_controller_initialize_test.dart',
             'chat_controller_notification_test.dart', 'chat_controller_active_job_summary_test.dart',
             'chat_controller_reviewer_state_test.dart', 'chat_controller_run_history_test.dart',
             'chat_screen_refresh_test.dart', 'chat_screen_attachment_composer_test.dart',
             'internal_chat_link_test.dart', 'api_client_test.dart']
    result = subprocess.run([shutil.which('flutter') or 'flutter', 'test', '--no-pub',
                             *['test/' + f for f in files], '--reporter=json'],
                            cwd=ROOT / 'frontend/mobile_app', capture_output=True,
                            text=True, timeout=240)
    REPORT.mkdir(parents=True, exist_ok=True)
    (REPORT / 'flutter-tests.jsonl').write_text(result.stdout + result.stderr)
    names, outcomes = {}, {}
    for line in result.stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if event.get('type') == 'testStart':
            names[event['test']['id']] = event['test']['name']
        if event.get('type') == 'testDone':
            outcomes[event['testID']] = event.get('result') == 'success' and not event.get('skipped', False)
    def passed_group(fragment):
        chosen = [i for i, name in names.items() if fragment in name]
        return bool(chosen) and all(outcomes.get(i, False) for i in chosen)
    observations = {
        'switch-responsive': passed_group('switch:'),
        'send-responsive': passed_group('send:'),
        'latency-evidence': result.returncode == 0 and passed_group('decode:')
    }
    tests = [i for i in outcomes if not names.get(i, '').startswith('loading ') and
             not names.get(i, '').endswith(('(setUpAll)', '(tearDownAll)'))]
    summary = {'target':'Local Flutter tests with controlled delayed API; not installed APK',
               'tests':len(tests), 'passed':sum(outcomes[i] for i in tests),
               'exit_code':result.returncode, 'observations':observations,
               'production_after':'Publication tracked separately; installed-device verification pending',
               'failed_tests':[names[i] for i in tests if not outcomes[i]]}
    (REPORT / 'executed-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps({'observations': observations}))
    return 0 if all(observations.values()) else 1

if __name__ == '__main__':
    sys.exit(main())

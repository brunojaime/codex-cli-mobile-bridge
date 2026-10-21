"""Exercise the real secrets widget with synthetic inputs and HTTP responses."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'reports/secrets-visibility-20261010'
result = subprocess.run(
    [shutil.which('flutter') or 'flutter', 'test', '--no-pub',
     'test/project_secrets_sheet_test.dart', '--reporter=json'],
    cwd=ROOT / 'frontend/mobile_app', capture_output=True, text=True, timeout=300,
)
(OUT / 'widget-check.jsonl').write_text(result.stdout + result.stderr)
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
tests = [i for i in outcomes if not names.get(i, '').startswith('loading ')]
visibility = [i for i in tests if names[i].startswith('visibility:')]
passed = result.returncode == 0 and len(visibility) == 2 and all(outcomes.values())
facts = {key: passed for key in ['toggle-input', 'reset-and-save', 'local-evidence']}
summary = {'target': 'local Flutter widget; synthetic data; no installed APK',
           'exit_code': result.returncode, 'tests': len(tests),
           'passed': sum(outcomes[i] for i in tests),
           'failed_tests': [names[i] for i in tests if not outcomes[i]], 'observations': facts}
(OUT / 'executed-summary.json').write_text(json.dumps(summary, indent=2) + '\n')
print(json.dumps(summary))
print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps({'observations': facts}))
sys.exit(0 if passed else 1)

#!/usr/bin/env python3
"""Execute local Flutter table checks and capture the real message widget."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / 'reports/mobile-tables-20261008'

def main():
    REPORT.mkdir(parents=True, exist_ok=True)
    result = subprocess.run([
        shutil.which('flutter') or 'flutter', 'test', '--no-pub',
        '--dart-define=CAPTURE_TABLE_LAYOUTS=true',
        'test/message_tables_test.dart', 'test/rich_message_content_test.dart',
        '--reporter=json',
    ], cwd=ROOT / 'frontend/mobile_app', capture_output=True, text=True, timeout=240)
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
    def group(fragment):
        selected = [id for id, name in names.items() if fragment in name]
        return bool(selected) and all(outcomes.get(id, False) for id in selected)
    captures = [REPORT / f'tables-{width}-{scale}x.png'
                for width in [360, 430, 768, 1440, 1728] for scale in [1, 2]]
    observations = {
        'markdown-tables': group('parse:') and group('actions: links'),
        'mobile-readable': group('layout:') and group('actions: mobile'),
        'regression-tests': result.returncode == 0 and group('streaming:') and group('selection copies'),
        'widget-captures': all(p.is_file() and p.stat().st_size > 1000 for p in captures),
    }
    summary = {'target': 'Local Flutter message widget; not an installed APK',
               'test_count': sum(1 for id in outcomes if not names[id].endswith(('(setUpAll)', '(tearDownAll)')) and not names[id].startswith('loading ')),
               'exit_code': result.returncode, 'observations': observations,
               'visual_review': 'Separate inspection in report; not inferred from test success'}
    (REPORT / 'executed-summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary, indent=2))
    print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps({'observations': observations}))
    return 0 if all(observations.values()) else 1

if __name__ == '__main__':
    sys.exit(main())

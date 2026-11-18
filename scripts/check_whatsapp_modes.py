#!/usr/bin/env python3
"""Run channel, catalog, regression and Flutter color checks locally."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
folder = root / 'reports/whatsapp-modes-20261026'
folder.mkdir(parents=True, exist_ok=True)
python_check = subprocess.run([
    sys.executable, '-m', 'pytest', 'tests/test_whatsapp_modes.py',
    'tests/test_whatsapp_intake_worker.py', 'tests/test_whatsapp_video.py', '-q',
], cwd=root, capture_output=True, text=True)
(folder / 'python-tests.txt').write_text(python_check.stdout + python_check.stderr)
flutter = shutil.which('flutter')
color_passed = False
if flutter:
    ui = subprocess.run([flutter, 'test', '--no-pub',
        'test/chat_screen_overflow_test.dart', '--plain-name', 'sidebar colors'],
        cwd=root / 'frontend/mobile_app', capture_output=True, text=True)
    (folder / 'flutter-tests.txt').write_text(ui.stdout + ui.stderr)
    color_passed = ui.returncode == 0
observations = {}
if python_check.returncode == 0:
    observations.update({'channel-dispatch': True, 'recent-catalog': True})
if color_passed:
    observations['origin-color'] = True
if python_check.returncode == 0 and color_passed:
    observations['local-evidence'] = True
print('NIENFOS_OBSERVATIONS_V1 ' + json.dumps({'observations': observations}))
raise SystemExit(0 if python_check.returncode == 0 and color_passed else 1)

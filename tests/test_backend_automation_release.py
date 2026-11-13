import json
from backend.app.application.services.backend_automation_release import read_revision


def test_only_full_revision_is_accepted(tmp_path):
    assert read_revision(tmp_path) is None
    folder = tmp_path / '.run/bridge-autofix'
    folder.mkdir(parents=True)
    file = folder / 'loaded-release.json'
    for invalid in ['bad', json.dumps({'commit': 'short'}), json.dumps({'commit': 1}), '{}']:
        file.write_text(invalid)
        assert read_revision(tmp_path) is None
    file.write_text(json.dumps({'commit': 'a' * 40}))
    assert read_revision(tmp_path) == 'a' * 40

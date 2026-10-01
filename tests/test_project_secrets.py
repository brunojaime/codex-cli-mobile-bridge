from __future__ import annotations

from pathlib import Path
import subprocess

from fastapi.testclient import TestClient

from backend.app.infrastructure.config.settings import Settings
from backend.app.main import create_app


def test_project_secret_api_is_write_only_and_lists_names(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "storefront"
    project.mkdir(parents=True)
    (project / ".env").write_text(
        "# Existing local configuration\nPUBLIC_MODE='real'\n",
        encoding="utf-8",
    )
    client = _client(projects_root)

    response = client.post(
        "/project-secrets",
        json={
            "workspace_path": str(project),
            "name": "WORDPRESS_PASSWORD",
            "value": (
                "test-only-value with symbols # $ ' and spaces\n"
                "FAKE_NAME=part-of-the-secret"
            ),
        },
    )

    assert response.status_code == 200, response.text
    assert response.json() == {
        "workspace_path": str(project),
        "workspace_name": "storefront",
        "env_file": ".env",
        "names": ["PUBLIC_MODE", "WORDPRESS_PASSWORD"],
    }
    assert "test-only-value" not in response.text
    env_content = (project / ".env").read_text(encoding="utf-8")
    assert "# Existing local configuration" in env_content
    assert "WORDPRESS_PASSWORD=" in env_content
    assert "test-only-value" in env_content
    assert "FAKE_NAME" not in response.json()["names"]
    assert (project / ".env").stat().st_mode & 0o777 == 0o600
    agent_guidance = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- codex-mobile-project-secrets -->" in agent_guidance
    assert "Secrets" in agent_guidance
    assert "test-only-value" not in agent_guidance

    listed = client.get(
        "/project-secrets",
        params={"workspace_path": str(project)},
    )
    assert listed.status_code == 200
    assert listed.json()["names"] == ["PUBLIC_MODE", "WORDPRESS_PASSWORD"]
    assert "test-only-value" not in listed.text


def test_project_secret_api_replaces_without_returning_previous_value(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "cms"
    project.mkdir(parents=True)
    client = _client(projects_root)

    first = client.post(
        "/project-secrets",
        json={
            "workspace_path": str(project),
            "name": "CMS_PASSWORD",
            "value": "first-test-value",
        },
    )
    second = client.post(
        "/project-secrets",
        json={
            "workspace_path": str(project),
            "name": "CMS_PASSWORD",
            "value": "rotated-test-value",
        },
    )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["names"] == ["CMS_PASSWORD"]
    assert "first-test-value" not in second.text
    assert "rotated-test-value" not in second.text
    env_content = (project / ".env").read_text(encoding="utf-8")
    assert "first-test-value" not in env_content
    assert "rotated-test-value" in env_content
    assert (
        (project / "AGENTS.md")
        .read_text(encoding="utf-8")
        .count("<!-- codex-mobile-project-secrets -->")
        == 1
    )


def test_project_secret_api_rejects_workspace_escape_and_env_symlink(
    tmp_path: Path,
) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "allowed"
    outside = tmp_path / "outside"
    project.mkdir(parents=True)
    outside.mkdir()
    client = _client(projects_root)

    escaped = client.post(
        "/project-secrets",
        json={
            "workspace_path": str(outside),
            "name": "TOKEN",
            "value": "test-value",
        },
    )
    assert escaped.status_code == 403
    assert not (outside / ".env").exists()

    target = tmp_path / "shared.env"
    target.write_text("SAFE='unchanged'\n", encoding="utf-8")
    (project / ".env").symlink_to(target)
    symlinked = client.post(
        "/project-secrets",
        json={
            "workspace_path": str(project),
            "name": "TOKEN",
            "value": "test-value",
        },
    )
    assert symlinked.status_code == 409
    assert target.read_text(encoding="utf-8") == "SAFE='unchanged'\n"


def test_project_secret_api_ignores_env_in_git_repository(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "git-project"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    client = _client(projects_root)

    response = client.post(
        "/project-secrets",
        json={
            "workspace_path": str(project),
            "name": "DEPLOY_TOKEN",
            "value": "test-only-deploy-token",
        },
    )

    assert response.status_code == 200, response.text
    assert "/.env" in (project / ".gitignore").read_text(encoding="utf-8")
    ignored = subprocess.run(
        ["git", "-C", str(project), "check-ignore", ".env"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert ignored.returncode == 0


def test_project_secret_api_rejects_tracked_env_file(tmp_path: Path) -> None:
    projects_root = tmp_path / "projects"
    project = projects_root / "tracked-project"
    project.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / ".env").write_text("TRACKED='placeholder'\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(project), "add", "-f", ".env"], check=True)
    client = _client(projects_root)

    response = client.post(
        "/project-secrets",
        json={
            "workspace_path": str(project),
            "name": "TOKEN",
            "value": "test-value",
        },
    )

    assert response.status_code == 409
    assert "tracked by Git" in response.json()["detail"]
    assert "TOKEN" not in (project / ".env").read_text(encoding="utf-8")


def _client(projects_root: Path) -> TestClient:
    settings = Settings(
        projects_root=str(projects_root),
        codex_workdir=str(projects_root),
        chat_store_backend="memory",
        audio_transcription_backend="disabled",
        speech_synthesis_backend="disabled",
        poll_interval_seconds=0,
        project_factory_reference_asset_dir=str(projects_root / ".assets"),
        project_factory_state_dir=str(projects_root / ".state"),
    )
    return TestClient(create_app(settings))


def test_edit_delete_preserve_literal_values_and_other_entries(tmp_path: Path) -> None:
    from dotenv import dotenv_values
    project = tmp_path / 'app'
    project.mkdir()
    env = project / '.env'
    env.write_text("# Keep comment\nOTHER='untouched'\nTOKEN='duplicate'\nTOKEN='literal ${OTHER}\\nline'\n")
    client = _client(tmp_path)
    original = dotenv_values(env, interpolate=False)['TOKEN']
    body = {'workspace_path': str(project), 'name': 'TOKEN', 'new_name': 'RENAMED'}
    response = client.patch('/project-secrets', json=body)
    assert response.status_code == 200
    assert response.json()['names'] == ['OTHER', 'RENAMED']
    assert dotenv_values(env, interpolate=False)['RENAMED'] == original
    assert 'literal' not in response.text
    assert 'TOKEN=' not in env.read_text()
    assert '# Keep comment' in env.read_text()
    assert env.stat().st_mode & 0o777 == 0o600
    rotated = "replacement with ' quotes\nand ${OTHER}"
    response = client.patch('/api/v1/project-secrets', json={
        **body, 'name': 'RENAMED', 'new_name': 'FINAL', 'value': rotated,
    })
    assert response.status_code == 200
    assert dotenv_values(env, interpolate=False) == {'OTHER': 'untouched', 'FINAL': rotated}
    assert rotated not in response.text
    response = client.delete('/project-secrets', params={'workspace_path': str(project), 'name': 'FINAL'})
    assert response.status_code == 200
    assert response.json()['names'] == ['OTHER']
    assert dotenv_values(env, interpolate=False) == {'OTHER': 'untouched'}
    assert '# Keep comment' in env.read_text()
    assert 'replacement' not in env.read_text()


def test_edit_collisions_missing_invalid_and_no_value_echo(tmp_path: Path) -> None:
    project = tmp_path / 'app'
    project.mkdir()
    env = project / '.env'
    env.write_text("FIRST='first-private'\nSECOND='second-private'\n")
    original = env.read_bytes()
    client = _client(tmp_path)
    body = {'workspace_path': str(project), 'name': 'FIRST', 'new_name': 'SECOND', 'value': 'do-not-echo'}
    assert client.patch('/project-secrets', json=body).status_code == 409
    assert client.patch('/project-secrets', json={**body, 'name': 'MISSING'}).status_code == 409
    assert client.delete('/project-secrets', params={'workspace_path': str(project), 'name': 'MISSING'}).status_code == 409
    for changes in ({'new_name': '9 invalid'}, {'value': ''}, {'value': {'private': 'do-not-echo'}}, {'value': 'do-not-echo\x00'}):
        response = client.patch('/project-secrets', json={**body, **changes})
        assert response.status_code in (409, 422)
        assert 'do-not-echo' not in response.text
        assert 'first-private' not in response.text
    response = client.post('/project-secrets', json={
        'workspace_path': str(project), 'name': 'FIRST', 'value': {'private': 'do-not-echo'},
    })
    assert response.status_code == 422
    assert 'do-not-echo' not in response.text
    assert env.read_bytes() == original


def test_edit_delete_reject_symlink_and_tracked_file(tmp_path: Path) -> None:
    project = tmp_path / 'app'
    project.mkdir()
    target = tmp_path / 'target.env'
    target.write_text("TOKEN='keep'\n")
    env = project / '.env'
    env.symlink_to(target)
    client = _client(tmp_path)
    body = {'workspace_path': str(project), 'name': 'TOKEN', 'new_name': 'NEW'}
    assert client.patch('/project-secrets', json=body).status_code == 409
    assert client.delete('/project-secrets', params={'workspace_path': str(project), 'name': 'TOKEN'}).status_code == 409
    assert target.read_text() == "TOKEN='keep'\n"
    env.unlink()
    env.write_text(target.read_text())
    subprocess.run(['git', 'init', '-q', str(project)], check=True)
    subprocess.run(['git', '-C', str(project), 'add', '-f', '.env'], check=True)
    assert client.patch('/project-secrets', json=body).status_code == 409
    assert client.delete('/project-secrets', params={'workspace_path': str(project), 'name': 'TOKEN'}).status_code == 409
    assert env.read_text() == "TOKEN='keep'\n"

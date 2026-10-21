import pytest
from scripts.activate_history_efficiency import fully_idle, verify_files, digest


def idle_status():
    return dict(
        requested=True,
        ready_to_restart=True,
        active_job_count=0,
        active_session_count=0,
        in_flight_message_count=0,
        active_jobs=[],
        active_session_ids=[],
        in_flight_message_ids=[],
        active_agent_run_ids=[],
        pending_follow_up_message_ids=[],
        unknown_blockers=[],
        sdd_codex_job_ids=[],
        project_factory_job_ids=[],
        domain_factory_job_ids=[],
    )


@pytest.mark.parametrize(
    "field",
    [
        "active_job_count",
        "active_session_count",
        "in_flight_message_count",
        "active_jobs",
        "active_session_ids",
        "in_flight_message_ids",
        "active_agent_run_ids",
        "pending_follow_up_message_ids",
        "unknown_blockers",
        "sdd_codex_job_ids",
        "project_factory_job_ids",
        "domain_factory_job_ids",
    ],
)
def test_never_restarts_with_work_or_missing_status(field):
    status = idle_status()
    assert fully_idle(status, drained=True)
    status[field] = 1 if field.endswith("count") else ["work"]
    assert not fully_idle(status, drained=True)
    del status[field]
    assert not fully_idle(status, drained=True)


def test_drain_must_be_owned_and_ready():
    status = idle_status()
    status["requested"] = False
    assert not fully_idle(status, drained=True)
    status["requested"] = True
    status["ready_to_restart"] = False
    assert not fully_idle(status, drained=True)


def test_source_drift_blocks_activation(tmp_path):
    root = tmp_path / "live"
    release = tmp_path / "release"
    root.mkdir()
    release.mkdir()
    (root / "code.py").write_text("old")
    (release / "code.py").write_text("new")
    manifest = {
        "baseline": {"code.py": digest(root / "code.py")},
        "files": {"code.py": digest(release / "code.py")},
    }
    verify_files(root, release, manifest)
    (root / "code.py").write_text("another conversation changed this")
    with pytest.raises(RuntimeError, match="Source changed"):
        verify_files(root, release, manifest)
    assert (root / "code.py").read_text() == "another conversation changed this"


def test_partial_install_restores_original_files(tmp_path, monkeypatch):
    from scripts import activate_history_efficiency as activation

    root = tmp_path / "live"
    release = tmp_path / "release"
    report = tmp_path / "report"
    root.mkdir()
    release.mkdir()
    report.mkdir()
    for name in ("a.py", "b.py"):
        (root / name).write_text("old")
        (release / name).write_text("new")
    original = activation.atomic_copy

    def fail_second(source, destination):
        if source == release / "b.py":
            raise OSError("simulated copy failure")
        original(source, destination)

    monkeypatch.setattr(activation, "atomic_copy", fail_second)
    with pytest.raises(OSError):
        activation.install_files(root, release, report, ["a.py", "b.py"])
    assert (root / "a.py").read_text() == (root / "b.py").read_text() == "old"

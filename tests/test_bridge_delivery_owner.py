import json
import pytest
from scripts.project_work import bridge_dev_delivery as operator


def setup_operator(tmp_path, monkeypatch, state, revision='a'*40):
    report=tmp_path/'report.json'; report.write_text(json.dumps({'state':state,'commit':revision}))
    config=tmp_path/'config.json';config.write_text(json.dumps({'checkout':str(tmp_path),'report':str(report)}))
    plan=tmp_path/'plan.json';plan.write_text(json.dumps({'revision':'a'*40}))
    monkeypatch.setattr(operator,'prepare',lambda *a,**kw:plan)
    monkeypatch.setattr(operator,'run',lambda *a,**kw:'')
    monkeypatch.setattr(operator.sys,'argv',['operator','deploy','--config',str(config)])
    monkeypatch.setattr(operator.time,'sleep',lambda _:None)


def test_prod_coordinator_returns_when_dev_activation_finishes(tmp_path,monkeypatch):
    setup_operator(tmp_path,monkeypatch,'published_and_verified')
    operator.main()


def test_uncertain_activation_is_never_reported_as_completed(tmp_path,monkeypatch):
    setup_operator(tmp_path,monkeypatch,'blocked_requires_inspection')
    with pytest.raises(RuntimeError,match='inspection'):operator.main()


def test_old_release_receipt_does_not_complete_new_delivery(tmp_path,monkeypatch):
    setup_operator(tmp_path,monkeypatch,'published_and_verified','b'*40)
    times=iter([0,0,841]);monkeypatch.setattr(operator.time,'monotonic',lambda:next(times))
    with pytest.raises(TimeoutError):operator.main()

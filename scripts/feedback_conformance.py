"""Compatibility entrypoint for the one packaged conformance engine."""
import importlib.util
from pathlib import Path
_spec = importlib.util.spec_from_file_location("codex_feedback_conformance", Path(__file__).resolve().parents[1] / "packages/codex-developer-feedback-web/tools/feedback_conformance.py")
_engine = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_engine)
assess = _engine.assess
main = _engine.main
if __name__ == '__main__':
    raise SystemExit(main())

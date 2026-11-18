"""Integration checks with two clones and a local bare remote; no network."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("handoff", Path(__file__).with_name("handoff.py"))
handoff = importlib.util.module_from_spec(spec)
spec.loader.exec_module(handoff)


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args], stderr=subprocess.DEVNULL, text=True).strip()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.remote, self.a, self.b = (root / name for name in ("remote.git", "a", "b"))
        git(root, "init", "--bare", "--initial-branch=main", str(self.remote))
        git(root, "clone", str(self.remote), str(self.a))
        self.configure(self.a)
        self.commit(self.a, "base")
        git(self.a, "push", "-u", "origin", "main")
        git(root, "clone", str(self.remote), str(self.b))
        self.configure(self.b)

    def configure(self, repo):
        git(repo, "config", "user.email", "test@example.invalid")
        git(repo, "config", "user.name", "Test")
        git(repo, "config", "commit.gpgsign", "false")
        git(repo, "config", "core.hooksPath", str(Path(self.temp.name) / "no-hooks"))

    def commit(self, repo, text):
        (repo / "app.txt").write_text(text)
        git(repo, "add", "app.txt")
        git(repo, "commit", "-m", text)

    def test_round_trip_between_machines(self):
        self.commit(self.a, "from Batata")
        handoff.sync(self.a, "finish")
        handoff.sync(self.b, "start")
        self.assertEqual((self.b / "app.txt").read_text(), "from Batata")
        self.commit(self.b, "from Lenovo")
        handoff.sync(self.b, "finish")
        handoff.sync(self.a, "start")
        self.assertEqual((self.a / "app.txt").read_text(), "from Lenovo")

    def test_dirty_work_is_preserved_and_not_uploaded(self):
        before = git(self.remote, "rev-parse", "main")
        (self.a / "app.txt").write_text("pending")
        (self.a / "untracked.txt").write_text("new")
        for action in ("start", "finish"):
            with self.assertRaises(handoff.HandoffError):
                handoff.sync(self.a, action)
        self.assertEqual(git(self.remote, "rev-parse", "main"), before)
        self.assertEqual((self.a / "app.txt").read_text(), "pending")
        self.assertTrue((self.a / "untracked.txt").exists())

    def test_diverged_branches_are_not_merged_or_pushed(self):
        self.commit(self.a, "a change")
        handoff.sync(self.a, "finish")
        self.commit(self.b, "b change")
        before = git(self.b, "rev-parse", "HEAD")
        for action in ("start", "finish"):
            with self.assertRaises(handoff.HandoffError):
                handoff.sync(self.b, action)
        self.assertEqual(git(self.b, "rev-parse", "HEAD"), before)

    def test_start_blocks_local_unpublished_commits(self):
        self.commit(self.a, "unpublished")
        with self.assertRaises(handoff.HandoffError):
            handoff.sync(self.a, "start")

    def test_finish_blocks_outdated_copy(self):
        self.commit(self.a, "new remote")
        handoff.sync(self.a, "finish")
        before = git(self.b, "rev-parse", "HEAD")
        with self.assertRaises(handoff.HandoffError):
            handoff.sync(self.b, "finish")
        self.assertEqual(git(self.b, "rev-parse", "HEAD"), before)


if __name__ == "__main__":
    unittest.main()

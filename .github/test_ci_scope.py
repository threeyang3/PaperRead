"""Exercise cost routing and real Git change ranges without starting application runtimes."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from ci_scope import changed_paths, classify

SCRIPT = Path(__file__).with_name("ci_scope.py").resolve()
CASES = [
    ("src/paperflow/text_quality.py", False),
    ("templates/Paper.md", False),
    ("prompts/analyze.md", False),
    ("src/paperflow/paths/service.py", True),
    ("requirements/release-py313.txt", True),
    ("integrations/obsidian-paperflow-automation/main.js", True),
    ("scripts/build_release.py", True),
]


class ScopeTests(unittest.TestCase):
    def test_documentation_and_mixed_changes(self):
        self.assertEqual(
            classify(["README.md", "docs/guide.md"]), {"code": False, "full": False, "docs": True}
        )
        self.assertFalse(classify([])["code"])
        for path, full in CASES:
            with self.subTest(path=path):
                result = classify(["docs/guide.md", path])
                self.assertTrue(result["code"])
                self.assertFalse(result["docs"])
                self.assertEqual(result["full"], full)
        self.assertTrue(classify(["new-unknown-tool.config"])["full"])
        self.assertTrue(classify([".github/ci_scope.py"])["full"])

    def test_git_ranges_renames_deletions_and_pr_merge_base(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            os.chdir(directory)
            try:

                def git(*args):
                    return (
                        subprocess.check_output(["git", *args], stderr=subprocess.DEVNULL)
                        .decode()
                        .strip()
                    )

                def commit(name):
                    git("add", "-A")
                    git("commit", "-m", name)
                    return git("rev-parse", "HEAD")

                git("init", "-b", "main")
                git("config", "user.email", "ci-test@example.invalid")
                git("config", "user.name", "CI scope test")
                Path("native.config").write_text("before\n")
                base = commit("base")
                Path("native.config").rename("README.md")
                commit("rename")
                Path("docs").mkdir()
                Path("docs/中文 guide.md").write_text("documentation\n")
                head = commit("docs after native change")
                paths = changed_paths("push", base, head)
                self.assertEqual(set(paths), {"native.config", "README.md", "docs/中文 guide.md"})
                self.assertTrue(classify(paths)["full"])
                self.assertIn("README.md", changed_paths("push", "0" * 40, head))
                git("checkout", "-b", "target", base)
                Path("target-only.config").write_text("target change\n")
                target = commit("target advanced")
                self.assertEqual(set(changed_paths("pull_request", target, head)), set(paths))
                with self.assertRaises(ValueError):
                    changed_paths("push", "invalid", head)
            finally:
                os.chdir(previous)

    def test_manual_and_tag_always_full_and_bad_event_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output"
            for event, ref in [
                ("workflow_dispatch", "refs/heads/main"),
                ("push", "refs/tags/1.2.3"),
            ]:
                output.write_text("")
                env = dict(os.environ, CI_EVENT=event, CI_REF=ref, GITHUB_OUTPUT=str(output))
                subprocess.run(
                    [os.sys.executable, str(SCRIPT)], env=env, check=True, capture_output=True
                )
                self.assertEqual(output.read_text(), "code=true\nfull=true\ndocs=false\n")
            env = dict(
                os.environ,
                CI_EVENT="push",
                CI_REF="refs/heads/main",
                CI_BASE="bad",
                CI_HEAD="bad",
                GITHUB_OUTPUT=str(output),
            )
            result = subprocess.run([os.sys.executable, str(SCRIPT)], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()

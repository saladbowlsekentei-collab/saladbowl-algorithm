import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from dressing import load_policy
from dressing.policy import DEFAULT_PATH


ROOT = Path(__file__).resolve().parent.parent


class PolicyTests(unittest.TestCase):
    def test_release_preserves_published_conditions(self):
        policy = load_policy()
        self.assertEqual(policy.livepocket_days, 14)
        self.assertEqual(policy.livepocket_posts, 10)
        self.assertEqual(policy.recovery_days, 5)
        self.assertEqual(policy.contribution_days, 14)
        self.assertEqual(policy.retention_shares, 1)
        self.assertEqual(policy.weights["honoa_quote_multiplier"], 2)
        self.assertIn("joshin", policy.excluded_sources)

    def test_bad_configurations_are_rejected(self):
        original = DEFAULT_PATH.read_text(encoding="utf-8")
        variants = [
            original.replace('analysis = "75"', 'analysis = "NaN"'),
            original.replace('analysis = "75"', 'analysis = "-1"'),
            original.replace('analysis = "75"', 'analysis = 75'),
            original.replace("recovery_days = 5", "recovery_days = 15"),
            original.replace("recovery_days = 5", "recovery_days = true"),
            original.replace('honoa_quote_multiplier = "2"', 'honoa_quote_multiplier = "0.5"'),
            original.replace('guest_access = "planned"', 'guest_access = "enabled"'),
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.toml"
            for index, text in enumerate(variants):
                with self.subTest(index=index):
                    path.write_text(text, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        load_policy(path)

    def test_readme_matches_configuration(self):
        run = subprocess.run([sys.executable, "tools/sync_readme.py", "--check"],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stderr)


class CliTests(unittest.TestCase):
    def run_cli(self, path):
        return subprocess.run([sys.executable, "-m", "dressing", str(path)],
                              cwd=ROOT, capture_output=True, text=True, timeout=15)

    def test_example_command_returns_valid_json(self):
        run = self.run_cli(ROOT / "examples/sample.json")
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stderr, "")
        self.assertEqual(json.loads(run.stdout)["policy_version"], "0.1.0")

    def test_bad_json_is_rejected_without_traceback(self):
        samples = [
            b"not json", b"\xff", b"null", b"{}",
            b'{"as_of": "2026-10-23T00:00:00Z", "members": [], "members": [], "events": []}',
            b'{"as_of": NaN, "members": [], "events": []}',
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for index, sample in enumerate(samples):
                with self.subTest(index=index):
                    path.write_bytes(sample)
                    run = self.run_cli(path)
                    self.assertEqual(run.returncode, 2)
                    self.assertEqual(run.stdout, "")
                    self.assertNotIn("Traceback", run.stderr)
                    self.assertNotIn(str(path), run.stderr)

    def test_missing_file_does_not_print_local_path(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "missing.json"
            run = self.run_cli(path)
            self.assertEqual(run.returncode, 2)
            self.assertNotIn(str(path), run.stderr)

    def test_oversized_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "large.json"
            path.write_bytes(b" " * (4 * 1024 * 1024 + 1))
            run = self.run_cli(path)
            self.assertEqual(run.returncode, 2)
            self.assertIn("exceeds", run.stderr)


if __name__ == "__main__":
    unittest.main()


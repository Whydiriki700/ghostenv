import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ghostenv

# Fixture source lines are built by concatenation so this test file does
# not itself match the patterns it tests for.
PY_SRC = "\n".join([
    "import os",
    'A = ' + 'os.env' + 'iron["USED_OK"]',
    'B = ' + 'os.get' + 'env("GHOST_KEY")',
    'C = ' + 'os.env' + 'iron.get("THIRD_KEY")',
    "",
])
JS_SRC = "\n".join([
    'const a = ' + 'process' + '.env.USED_OK;',
    'const b = ' + 'process' + '.env.JS_GHOST;',
    "",
])


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(os.path.join(self.root, "app.py"), PY_SRC)
        write(os.path.join(self.root, "web.js"), JS_SRC)
        write(os.path.join(self.root, ".env.example"),
              "USED_OK=\nTHIRD_KEY=\nSTALE_KEY=\n")
        write(os.path.join(self.root, ".env"), "USED_OK=secret\n")

    def tearDown(self):
        self.tmp.cleanup()

    def report(self):
        return ghostenv.analyze(self.root)


class TestAnalyze(Fixture):
    def test_ghosts(self):
        self.assertEqual(self.report()["ghosts"], ["GHOST_KEY", "JS_GHOST"])

    def test_stale(self):
        self.assertEqual(self.report()["stale"], ["STALE_KEY"])

    def test_ok(self):
        self.assertIn("USED_OK", self.report()["ok"])

    def test_unset(self):
        self.assertEqual(self.report()["unset"], ["THIRD_KEY"])

    def test_main_exit_one_on_ghosts(self):
        self.assertEqual(ghostenv.main(["--root", self.root]), 1)


class TestClean(unittest.TestCase):
    def test_clean_project(self):
        with tempfile.TemporaryDirectory() as root:
            write(os.path.join(root, "app.py"),
                  'import os\nA = ' + 'os.get' + 'env("ONLY_KEY")\n')
            write(os.path.join(root, ".env.example"), "ONLY_KEY=\n")
            report = ghostenv.analyze(root)
            self.assertEqual(report["ghosts"], [])
            self.assertEqual(ghostenv.main(["--root", root]), 0)


class TestNamesOnly(unittest.TestCase):
    def test_values_never_in_report(self):
        with tempfile.TemporaryDirectory() as root:
            write(os.path.join(root, ".env"), "SOME_KEY=topsecretvalue\n")
            report = ghostenv.analyze(root)
            self.assertNotIn("topsecretvalue", str(report))


if __name__ == "__main__":
    unittest.main()

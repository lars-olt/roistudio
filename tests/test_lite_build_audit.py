import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    'lite_build_audit',
    ROOT / 'packaging' / 'audit_lite_build.py',
)
AUDIT_MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT_MODULE)
audit = AUDIT_MODULE.audit


class LiteBuildAuditTests(unittest.TestCase):
    def setUp(self):
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self.root = Path(self._temporary_directory.name)
        self.dist = self.root / 'dist'
        self.toc = self.root / 'PYZ-00.toc'
        self.dist.mkdir()
        self.toc.write_text("[('controllers.controller', 'controller.py')]", encoding='utf-8')

    def test_clean_bundle_passes(self):
        (self.dist / 'ROIStudio Lite.exe').touch()

        audit(self.dist, self.toc)

    def test_algorithm_distribution_in_bundle_fails(self):
        forbidden = self.dist / '_internal' / 'torch-2.2.2.dist-info'
        forbidden.mkdir(parents=True)

        with self.assertRaisesRegex(SystemExit, 'banned bundle path'):
            audit(self.dist, self.toc)

    def test_algorithm_module_in_toc_fails(self):
        self.toc.write_text("[('sklearn.cluster', 'cluster.py')]", encoding='utf-8')

        with self.assertRaisesRegex(SystemExit, 'banned analyzed module: sklearn.cluster'):
            audit(self.dist, self.toc)

    def test_missing_inputs_report_both_failures(self):
        self.dist.rmdir()
        self.toc.unlink()

        with self.assertRaises(SystemExit) as raised:
            audit(self.dist, self.toc)

        message = str(raised.exception)
        self.assertIn('missing Lite distribution', message)
        self.assertIn('missing PyInstaller module TOC', message)


if __name__ == '__main__':
    unittest.main()

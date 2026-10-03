import importlib.util
from pathlib import Path
import tempfile
import unittest


class ReleaseExclusionTests(unittest.TestCase):
    def test_bundle_audit_rejects_modules_and_weights(self):
        root = Path(__file__).parents[1]
        spec = importlib.util.spec_from_file_location('experimental_audit', root / 'packaging/audit_experimental_build.py')
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory) / 'dist'
            dist.mkdir()
            toc = Path(directory) / 'PYZ-00.toc'
            toc.write_text("[('controllers.controller', 'controller.py')]")
            audit.audit(dist, toc)
            toc.write_text("[('romatch.models.matcher', 'matcher.py')]")
            with self.assertRaisesRegex(SystemExit, 'experimental analyzed module'):
                audit.audit(dist, toc)
            toc.write_text("[('sparc.experimental.roma', 'roma.py')]")
            with self.assertRaisesRegex(SystemExit, 'experimental analyzed module'):
                audit.audit(dist, toc)
            toc.write_text('[]')
            (dist / 'roma_outdoor.pth').touch()
            with self.assertRaisesRegex(SystemExit, 'experimental weights'):
                audit.audit(dist, toc)


if __name__ == '__main__':
    unittest.main()

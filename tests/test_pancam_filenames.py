import ast
import re
import unittest
from pathlib import Path


def _scanner_pancam_pattern():
    path = Path(__file__).parents[1] / 'workers' / 'scene_scanner.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == '_PCAM_FILENAME_RE':
            return node.value.args[0].value
    raise AssertionError('Scene scanner Pancam filename pattern was not found')


# Real archive filenames can use placeholders where site and position would be.
class PancamFilenameTests(unittest.TestCase):
    def test_scanner_accepts_archive_site_position_placeholders(self):
        pattern = re.compile(_scanner_pancam_pattern(), re.IGNORECASE | re.VERBOSE)

        self.assertIsNotNone(
            pattern.match('2p228988949iofas__p2580l2a1.img')
        )
        self.assertIsNotNone(
            pattern.match('2p228988949iofas##p2580l2a1.img')
        )


if __name__ == '__main__':
    unittest.main()

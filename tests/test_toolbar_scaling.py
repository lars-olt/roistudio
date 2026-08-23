import ast
import unittest
from pathlib import Path


# Keep toolbar controls readable without letting Retina scaling make them huge.
class ToolbarScalingTests(unittest.TestCase):
    @staticmethod
    def _numeric_constants(path):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        return {
            node.targets[0].id: node.value.value
            for node in tree.body
            if isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, (int, float))
        }

    def test_toolbar_and_cursor_use_logical_application_scaling(self):
        root = Path(__file__).parents[1]
        files = [
            root / 'views' / 'widgets.py',
            root / 'views' / 'panels' / 'image_editing.py',
        ]

        for path in files:
            tree = ast.parse(path.read_text(encoding='utf-8'))
            physical_calls = [
                node for node in ast.walk(tree)
                if isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == 'physical'
            ]
            self.assertEqual(
                physical_calls, [],
                f'{path.name} must use logical scaled() dimensions so Qt '
                'handles Retina and remote-display DPI consistently',
            )

    def test_scene_thumbnails_use_capped_logical_application_scaling(self):
        # Thumbnails need one explicit logical size and one explicit upper limit.
        path = (Path(__file__).parents[1] / 'views' / 'panels' /
                'image_selection.py')
        tree = ast.parse(path.read_text(encoding='utf-8'))

        physical_calls = [
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == 'physical'
        ]
        self.assertEqual(physical_calls, [])

        panel = next(
            node for node in tree.body
            if isinstance(node, ast.ClassDef)
            and node.name == 'ImageSelectionPanel'
        )
        layout = next(
            node for node in panel.body
            if isinstance(node, ast.FunctionDef)
            and node.name == '_layout_params'
        )
        thumbnail_assignment = next(
            node for node in layout.body
            if isinstance(node, ast.Assign)
            and any(
                isinstance(target, ast.Name) and target.id == 'thumb'
                for target in node.targets
            )
        )

        call = thumbnail_assignment.value
        self.assertIsInstance(call, ast.Call)
        self.assertIsInstance(call.func, ast.Name)
        self.assertEqual(call.func.id, 'capped_scaled')
        self.assertEqual(
            [argument.id for argument in call.args],
            ['_THUMB_BASE', '_THUMB_MAX'],
            'The scene thumbnail dimension must use its explicit maximum',
        )

    def test_selection_cursor_starts_compact_and_has_a_small_cap(self):
        path = (Path(__file__).parents[1] / 'views' / 'panels' /
                'image_editing.py')
        constants = self._numeric_constants(path)
        self.assertEqual(constants['_CURSOR_NATIVE_W'], 24)
        self.assertEqual(constants['_CURSOR_MAX_W'], 28)


if __name__ == '__main__':
    unittest.main()

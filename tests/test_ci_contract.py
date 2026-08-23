import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


class ContinuousDeliveryContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ci = (ROOT / '.github' / 'workflows' / 'ci.yml').read_text(
            encoding='utf-8',
        )
        cls.build = (ROOT / '.github' / 'workflows' / 'build.yml').read_text(
            encoding='utf-8',
        )

    def test_ci_runs_for_changes_to_main(self):
        self.assertIn('pull_request:', self.ci)
        self.assertIn('branches: [main]', self.ci)
        self.assertIn('windows-latest', self.ci)
        self.assertIn('macos-14', self.ci)

    def test_release_builds_both_editions_on_both_platforms(self):
        expected_artifacts = {
            'ROIStudio-windows-x64',
            'ROIStudio-Lite-windows-x64',
            'ROIStudio-macos-silicon',
            'ROIStudio-Lite-macos-silicon',
        }
        for artifact in expected_artifacts:
            self.assertIn(f'artifact_name: {artifact}', self.build)

    def test_release_preserves_macos_bundle_symlinks(self):
        self.assertIn('zip -yr', self.build)

    def test_release_tag_must_match_project_version(self):
        self.assertIn('Verify release tag matches project version', self.build)
        self.assertIn('GITHUB_REF_NAME', self.build)

    def test_full_development_install_requests_algorithm_extra(self):
        project = tomllib.loads((ROOT / 'pyproject.toml').read_text(encoding='utf-8'))
        sparc = next(
            dependency
            for dependency in project['project']['dependencies']
            if dependency.startswith('sparc')
        )
        self.assertTrue(sparc.startswith('sparc[algorithm]'))


if __name__ == '__main__':
    unittest.main()

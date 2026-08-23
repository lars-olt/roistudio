import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
SETUP_UV_ACTION = (
    'astral-sh/setup-uv@c771a70e6277c0a99b617c7a806ffedaca235ff9'
)


# These are the release rules I do not want the workflow to silently lose.
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

    def test_uv_action_uses_an_immutable_release(self):
        # setup-uv does not publish moving tags like v9, so this must stay exact.
        for workflow in (self.ci, self.build):
            self.assertIn(f'uses: {SETUP_UV_ACTION}', workflow)
            self.assertNotIn('astral-sh/setup-uv@v', workflow)

    def test_release_builds_both_editions_on_both_platforms(self):
        expected_artifacts = {
            'ROIStudio-windows-x64',
            'ROIStudio-Lite-windows-x64',
            'ROIStudio-macos-silicon',
            'ROIStudio-Lite-macos-silicon',
        }
        for artifact in expected_artifacts:
            self.assertIn(f'artifact_name: {artifact}', self.build)
            self.assertIn(
                f'artifacts/{artifact}/{artifact}.zip',
                self.build,
                f'{artifact} must be attached to the GitHub release',
            )

    def test_packaged_applications_are_smoke_tested_before_upload(self):
        # Every uploaded app should have proved that it can at least start.
        smoke_commands = (
            '& "dist\\${{ matrix.product_name }}\\'
            '${{ matrix.product_name }}.exe" --smoke-test',
            '"dist/${{ matrix.product_name }}.app/Contents/MacOS/'
            '${{ matrix.product_name }}" --smoke-test',
        )
        upload_step = self.build.index('- name: Upload artifact')

        for command in smoke_commands:
            self.assertIn(command, self.build)
            self.assertLess(
                self.build.index(command),
                upload_step,
                'Only a packaged application that starts successfully may be uploaded',
            )

    def test_lite_bundle_is_audited_for_algorithm_dependencies(self):
        # Lite is only Lite if the heavy algorithm packages stay out of it.
        self.assertIn(
            '- name: Verify Lite excludes algorithm dependencies',
            self.build,
        )
        self.assertIn(
            'python packaging/audit_lite_build.py '
            '--dist "dist/${{ matrix.product_name }}" '
            '--module-toc build/roistudio/PYZ-00.toc',
            self.build,
        )

    def test_release_candidate_is_tested_after_building_before_release(self):
        # Build first, run the regular CI suite, and only then publish a release.
        build_job = self.build.index('\n  build:')
        test_job = self.build.index('\n  test:')
        release_job = self.build.index('\n  release:')

        self.assertIn('workflow_call:', self.ci)
        self.assertIn('name: Test release candidate', self.build)
        self.assertIn('needs: build', self.build)
        self.assertIn('uses: ./.github/workflows/ci.yml', self.build)
        self.assertIn('needs: [build, test]', self.build)
        self.assertLess(build_job, test_job)
        self.assertLess(test_job, release_job)

    def test_release_preserves_macos_bundle_symlinks(self):
        self.assertIn('zip -yr', self.build)

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

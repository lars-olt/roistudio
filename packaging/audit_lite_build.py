"""Fail a Lite build if algorithm modules or libraries entered the bundle."""

import argparse
from pathlib import Path
import re


BANNED_MODULES = (
    'torch',
    'torchvision',
    'segment_anything',
    'sklearn',
    'kneed',
    'psutil',
    'controllers.algorithm_controller',
    'controllers.sparc_callbacks',
    'workers.sparc_runner',
    'sparc.core.functional',
    'sparc.core.pipeline',
    'sparc.segmentation',
    'sparc.spectral',
)

BANNED_BUNDLE_PATHS = (
    'torch',
    'torchvision',
    'segment_anything',
    'sklearn',
    'kneed',
    'psutil',
)


def _is_banned(module_name):
    value = module_name.lower()
    return any(value == banned or value.startswith(f'{banned}.')
               for banned in BANNED_MODULES)


def audit(dist_path, module_toc_path):
    failures = []
    if not dist_path.is_dir():
        failures.append(f'missing Lite distribution: {dist_path}')
    else:
        for path in dist_path.rglob('*'):
            relative = path.relative_to(dist_path).as_posix().lower()
            parts = relative.split('/')
            if any(
                part == banned
                or part.startswith(f'{banned}.')
                or part.startswith(f'{banned}-')
                for part in parts
                for banned in BANNED_BUNDLE_PATHS
            ):
                failures.append(f'banned bundle path: {relative}')

    if not module_toc_path.is_file():
        failures.append(f'missing PyInstaller module TOC: {module_toc_path}')
    else:
        module_toc = module_toc_path.read_text(
            encoding='utf-8', errors='replace'
        )
        quoted_names = re.findall(
            r"['\"]([A-Za-z0-9_.-]+)['\"]", module_toc
        )
        leaked = sorted({name for name in quoted_names if _is_banned(name)})
        failures.extend(f'banned analyzed module: {name}' for name in leaked)

    if failures:
        raise SystemExit('\n'.join(failures))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--module-toc', type=Path, required=True)
    args = parser.parse_args()
    audit(args.dist, args.module_toc)
    print('ROIStudio Lite dependency audit passed')


if __name__ == '__main__':
    main()

"""Reject experimental RoMa code, dependencies, or weights in either edition."""

import argparse
from pathlib import Path
import re

BANNED = ('sparc.experimental', 'romatch', 'local_corr', 'fused_local_corr', 'fused-local-corr')


def audit(dist_path, module_toc_path):
    failures = []
    if not dist_path.is_dir():
        failures.append(f'missing distribution: {dist_path}')
    else:
        for path in dist_path.rglob('*'):
            parts = path.relative_to(dist_path).as_posix().lower().split('/')
            module_path = '.'.join(parts)
            if any(part == name or part.startswith(name + '.') or part.startswith(name + '-')
                   for part in parts for name in BANNED) or 'sparc.experimental' in module_path:
                failures.append(f'experimental bundle path: {path}')
            if path.name.lower() in ('roma_outdoor.pth', 'roma_indoor.pth', 'dinov2_vitl14_pretrain.pth'):
                failures.append(f'experimental weights: {path}')
    if not module_toc_path.is_file():
        failures.append(f'missing module TOC: {module_toc_path}')
    else:
        names = re.findall(r"['\"]([A-Za-z0-9_.-]+)['\"]", module_toc_path.read_text(encoding='utf-8'))
        for name in sorted(set(names)):
            if any(name == banned or name.startswith(banned + '.') for banned in BANNED):
                failures.append(f'experimental analyzed module: {name}')
    if failures:
        raise SystemExit('\n'.join(failures))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', type=Path, required=True)
    parser.add_argument('--module-toc', type=Path, required=True)
    args = parser.parse_args()
    audit(args.dist, args.module_toc)
    print('Experimental dependency audit passed')

"""Replace FITS metadata values and report files containing a selected value."""

import argparse
import csv
import re
from pathlib import Path

from astropy.io import fits


BACKUP_PREFIX = "OLD_METADATA_"
VERSION_SUFFIX = re.compile(r"_v(\d+)$", re.IGNORECASE)


def parse_replacement(value):
    """Parse an old=new command-line value."""
    if "=" not in value:
        raise argparse.ArgumentTypeError("must use OLD=NEW")

    old, new = (part.strip() for part in value.split("=", 1))
    if not old or not new:
        raise argparse.ArgumentTypeError("OLD and NEW must not be empty")
    return old.lower(), new


def replace_values(hdul, key, replacements):
    """Replace matching header values and describe each change."""
    changes = []

    for index, hdu in enumerate(hdul):
        header = hdu.header
        if key not in header:
            continue

        old_value = str(header[key]).strip()
        new_value = replacements.get(old_value.lower())
        if new_value is None:
            continue

        header[key] = new_value
        name = str(header.get("EXTNAME", header.get("NAME", f"HDU {index}")))
        changes.append(f"{name}: {old_value!r} -> {new_value!r}")

    return changes


def observation_name(path):
    """Return the observation name and saved version."""
    folder_name = path.parent.name
    match = VERSION_SUFFIX.search(folder_name)
    if match is None:
        return folder_name, 1
    return folder_name[:match.start()], int(match.group(1))


def find_observations(hdul, path, key, value):
    """Return the visible ROIs matching value."""
    rois = {}
    for index, hdu in enumerate(hdul):
        header = hdu.header
        if "NAME" not in header or "EYE" not in header:
            continue

        roi_name = str(header["NAME"]).strip() or f"HDU {index}"
        eye = str(header["EYE"]).strip().lower()
        metadata_value = str(header.get(key, "")).strip()
        rois.setdefault(roi_name.lower(), {})[eye] = (roi_name, metadata_value)

    name, version = observation_name(path)
    rows = []
    for eyes in rois.values():
        visible = eyes.get("right") or eyes.get("left")
        if visible is None or visible[1].lower() != value.lower():
            continue

        rows.append({
            "file_path": str(path.resolve()),
            "observation": name,
            "roi_name": visible[0],
        })

    identity = (str(path.parent.parent.resolve()).lower(), name.lower())
    return identity, version, rows


def next_backup_path(path):
    """Return an unused backup path beside the FITS file."""
    candidate = path.with_name(f"{BACKUP_PREFIX}{path.name}")
    number = 2
    while candidate.exists():
        candidate = path.with_name(f"{BACKUP_PREFIX}{number}_{path.name}")
        number += 1
    return candidate


def process_file(path, key, replacements, report_value):
    """Update one file."""
    temp_path = path.with_name(f"{path.name}.metadata_tmp")

    with fits.open(path) as hdul:
        observations = find_observations(hdul, path, key, report_value)
        changes = replace_values(hdul, key, replacements)
        if not changes:
            return "unchanged", changes, observations

        if temp_path.exists():
            temp_path.unlink()
        hdul.writeto(temp_path)

    path.replace(next_backup_path(path))
    temp_path.replace(path)
    return "converted", changes, observations


def iter_fits_files(root):
    """Yield every active FITS file below root."""
    for path in sorted(root.rglob("*")):
        if (
            path.is_file()
            and path.suffix.lower() == ".fits"
            and not path.name.startswith("OLD_")
        ):
            yield path


def write_report(observations, output_path):
    """Write a CSV report."""
    columns = (
        "file_path",
        "observation",
        "roi_name",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(sorted(
            observations,
            key=lambda row: (
                row["observation"].lower(),
                row["roi_name"].lower(),
                row["file_path"].lower(),
            ),
        ))


def current_observations(candidates):
    """Return matching ROIs from each observation's newest saved version."""
    current = {}
    for identity, version, rows in candidates:
        previous = current.get(identity)
        if previous is None or version > previous[0]:
            current[identity] = (version, rows)

    return [
        row
        for _, rows in current.values()
        for row in rows
    ]


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        type=Path,
        help="directory to scan",
    )
    parser.add_argument(
        "--key",
        required=True,
        help="FITS header key to update",
    )
    parser.add_argument(
        "--replace",
        action="append",
        type=parse_replacement,
        metavar="OLD=NEW",
        help="replacement to apply; omit for report-only use",
    )
    parser.add_argument(
        "--report-value",
        required=True,
        help="value to list in the CSV report",
    )
    parser.add_argument(
        "--report",
        type=Path,
        required=True,
        help="CSV output path",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    if not args.root.is_dir():
        raise FileNotFoundError(f"Directory not found: {args.root}")

    key = args.key.strip().upper()
    replacements = dict(args.replace or ())
    report_candidates = []
    counts = {
        "converted": 0,
        "unchanged": 0,
        "failed": 0,
    }

    for path in iter_fits_files(args.root):
        try:
            status, changes, matches = process_file(
                path,
                key,
                replacements,
                args.report_value,
            )
            counts[status] += 1
            report_candidates.append(matches)

            if changes:
                print(f"{status.upper()}: {path}")
                for change in changes:
                    print(f"    {change}")
        except Exception as exc:
            counts["failed"] += 1
            print(f"FAILED: {path}")
            print(f"    {type(exc).__name__}: {exc}")

    observations = current_observations(report_candidates)
    write_report(observations, args.report)

    print("\nDone")
    for status, count in counts.items():
        if count:
            print(f"    {status}: {count}")
    print(f"    matching ROIs: {len(observations)}")
    print(f"    report: {args.report.resolve()}")


if __name__ == "__main__":
    main()

"""Replace FITS metadata values and report files containing a selected value."""

import argparse
import csv
from pathlib import Path

from astropy.io import fits


BACKUP_PREFIX = "OLD_METADATA_"


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


def find_observations(hdul, path, key, value):
    """Return one row per matching ROI."""
    observations = {}

    for index, hdu in enumerate(hdul):
        header = hdu.header
        if str(header.get(key, "")).strip().lower() != value.lower():
            continue

        roi_name = str(header.get("NAME", header.get("EXTNAME", f"HDU {index}"))).strip()
        image_ref = str(header.get("IMAGEREF", "")).strip()
        identity = (roi_name.lower(), image_ref.lower())
        observations.setdefault(identity, {
            "file_path": str(path.resolve()),
            "image_ref": image_ref,
            "roi_name": roi_name,
        })

    return list(observations.values())


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
    for path in root.rglob("*"):
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
        "image_ref",
        "roi_name",
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        writer.writerows(sorted(
            observations,
            key=lambda row: (
                row["file_path"].lower(),
                row["image_ref"].lower(),
                row["roi_name"].lower(),
            ),
        ))


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
        required=True,
        metavar="OLD=NEW",
        help="replacement to apply; repeat for multiple values",
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
    replacements = dict(args.replace)
    observations = []
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
            observations.extend(matches)

            if changes:
                print(f"{status.upper()}: {path}")
                for change in changes:
                    print(f"    {change}")
        except Exception as exc:
            counts["failed"] += 1
            print(f"FAILED: {path}")
            print(f"    {type(exc).__name__}: {exc}")

    write_report(observations, args.report)

    print("\nDone")
    for status, count in counts.items():
        if count:
            print(f"    {status}: {count}")
    print(f"    matching observations: {len(observations)}")
    print(f"    report: {args.report.resolve()}")


if __name__ == "__main__":
    main()

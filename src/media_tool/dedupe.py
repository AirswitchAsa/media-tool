import os
from pathlib import Path
from datetime import datetime
from exiftool import ExifToolHelper
import click
from tqdm import tqdm
from multiprocessing import Pool, cpu_count
from collections import defaultdict

RAW_EXTENSIONS = [".raf", ".arw", ".dng", ".cr2", ".nef", ".orf", ".rw2"]
VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".m4v"]
IMAGE_EXTENSIONS = (
    [".jpg", ".jpeg", ".png", ".tiff"] + RAW_EXTENSIONS + VIDEO_EXTENSIONS
)


def get_exif_creation_date_pyexiftool(file_path):
    """Extracts the creation date using PyExifTool for both RAW and standard images."""
    # Check various EXIF date fields for the most relevant date
    date_tags = [
        "EXIF:DateTimeOriginal",  # Most common
        "QuickTime:CreateDate",  # For some video/photo formats
        "Composite:DateTimeCreated",  # Composite metadata
    ]
    try:
        with ExifToolHelper() as et:
            metadata_list = et.get_metadata(file_path)
            if not metadata_list:
                return None
            metadata = metadata_list[0]  # Get the first (and only) metadata dictionary

        for tag in date_tags:
            if tag in metadata:
                try:
                    return datetime.strptime(metadata[tag], "%Y:%m:%d %H:%M:%S").date()
                except ValueError:
                    pass  # Skip if parsing fails
    except Exception:
        pass  # Skip if exiftool fails

    return None


def get_file_creation_date(file_path):
    """Gets the file's creation date, falling back to modification date if needed."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(file_path)).date()
    except Exception:
        return None


def get_file_signature(file_path):
    """Get a file signature based on size and creation date."""
    try:
        file_stat = os.stat(file_path)
        file_size = file_stat.st_size
        creation_date = get_exif_creation_date_pyexiftool(
            file_path
        ) or get_file_creation_date(file_path)

        if creation_date:
            return (file_size, creation_date)
        return (file_size, None)
    except Exception:
        return None


def process_file(file_path):
    """Process a single file to get its signature - used by multiprocessing."""
    signature = get_file_signature(file_path)
    if signature:
        return (signature, file_path)
    return None


def find_duplicate_files(source_folder):
    """Find duplicate files based on size and creation date."""
    source_path = Path(source_folder)

    if not source_path.exists() or not source_path.is_dir():
        print("Source folder does not exist or is not a directory.")
        return {}

    # Find all media files
    media_files = []
    for ext in IMAGE_EXTENSIONS:
        media_files.extend(source_path.rglob(f"*{ext}"))
        media_files.extend(source_path.rglob(f"*{ext.upper()}"))

    if not media_files:
        print("No media files found in the source directory.")
        return {}

    # Use multiprocessing to speed up file signature calculation
    num_processes = min(cpu_count(), 8)  # Use up to 8 processes

    # Group files by signature (size and creation date)
    file_groups = defaultdict(list)

    with Pool(processes=num_processes) as pool:
        results = list(
            tqdm(
                pool.imap(process_file, media_files),
                total=len(media_files),
                desc="Scanning files",
                unit="file",
            )
        )

        # Process results
        for result in results:
            if result:
                signature, file_path = result
                file_groups[signature].append(file_path)

    # Filter out groups with only one file (no duplicates)
    duplicate_groups = {
        sig: files for sig, files in file_groups.items() if len(files) > 1
    }

    return duplicate_groups


def dedupe_all(duplicate_groups):
    """Delete all duplicates, keeping the file with the shortest name in each group."""
    deleted_count = 0

    for signature, files in duplicate_groups.items():
        # Sort files by name length (ascending)
        sorted_files = sorted(files, key=lambda x: len(str(x)))

        # Keep the first file (shortest name), delete the rest
        for file_to_delete in sorted_files[1:]:
            try:
                os.remove(file_to_delete)
                print(f"Deleted: {file_to_delete}")
                deleted_count += 1
            except Exception as e:
                print(f"Error deleting {file_to_delete}: {e}")

    return deleted_count


def review_and_dedupe(duplicate_groups):
    """Review each duplicate group and let the user decide what to delete."""
    deleted_count = 0

    for signature, files in duplicate_groups.items():
        print("\n" + "=" * 80)
        print(f"Duplicate group with {len(files)} files:")
        print(f"Size: {signature[0]} bytes, Date: {signature[1]}")

        # Sort files by name length (ascending)
        sorted_files = sorted(files, key=lambda x: len(str(x)))

        # Display all files in the group
        for i, file_path in enumerate(sorted_files):
            print(f"{i + 1}. {file_path}")

        # Highlight which file will be kept (shortest name)
        print(f"\nWill keep: {sorted_files[0]} (shortest name)")
        print(f"Will delete: {len(sorted_files) - 1} file(s)")

        # Ask for user confirmation
        while True:
            choice = input("Dedupe this group? (y=yes, n=skip, q=quit): ").lower()

            if choice == "y":
                for file_to_delete in sorted_files[1:]:
                    try:
                        os.remove(file_to_delete)
                        print(f"Deleted: {file_to_delete}")
                        deleted_count += 1
                    except Exception as e:
                        print(f"Error deleting {file_to_delete}: {e}")
                break
            elif choice == "n":
                print("Skipped.")
                break
            elif choice == "q":
                print("Quitting review process.")
                return deleted_count

    return deleted_count


@click.command()
@click.argument(
    "source",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
def cli(source: Path) -> None:
    """De-duplicate media files based on size and creation date."""
    print(f"Scanning for duplicate media files in: {source}")

    duplicate_groups = find_duplicate_files(source)

    if not duplicate_groups:
        print("No duplicates found.")
        return

    # Count total duplicates
    total_duplicates = sum(len(files) - 1 for files in duplicate_groups.values())
    duplicate_groups_count = len(duplicate_groups)

    print(
        f"\nFound {total_duplicates} duplicate files in {duplicate_groups_count} groups."
    )

    # Ask user what to do
    while True:
        action = input(
            "What would you like to do? (y=dedupe all, r=review, q=quit): "
        ).lower()

        if action == "y":
            deleted = dedupe_all(duplicate_groups)
            print(f"\nDeduplication complete. Deleted {deleted} files.")
            break
        elif action == "r":
            deleted = review_and_dedupe(duplicate_groups)
            print(f"\nReview complete. Deleted {deleted} files.")
            break
        elif action == "q":
            print("Exiting without deduplication.")
            break
        else:
            print("Invalid choice. Please try again.")


if __name__ == "__main__":
    cli()

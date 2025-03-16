import os
import shutil
from pathlib import Path
from datetime import datetime
from exiftool import ExifToolHelper
import click
from tqdm import tqdm
from multiprocessing import Pool, cpu_count

RAW_EXTENSIONS = [".raf", ".arw", ".dng", ".cr2", ".nef", ".orf", ".rw2"]
VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".m4v"]
IMAGE_EXTENSIONS = (
    [".jpg", ".jpeg", ".png", ".tiff", ".hif", ".heic"]
    + RAW_EXTENSIONS
    + VIDEO_EXTENSIONS
)


def get_exif_creation_date_pyexiftool(file_path):
    """Extracts the creation date using PyExifTool for both RAW and standard images."""

    # Check various EXIF date fields for the most relevant date
    date_tags = [
        "EXIF:DateTimeOriginal",  # Most common
        "QuickTime:CreateDate",  # For some video/photo formats
        "Composite:DateTimeCreated",  # Composite metadata
    ]
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

    return None


def get_file_creation_date(file_path):
    """Gets the file's creation date, falling back to modification date if needed."""
    try:
        return datetime.fromtimestamp(os.path.getmtime(file_path)).date()
    except Exception as e:
        print(f"Error getting modification time for {file_path}: {e}")
        return None


def process_single_image(args):
    """Process a single media file - used by the multiprocessing pool."""
    image_file, target_path, by_month, dry_run = args
    try:
        # Skip if the file is already in a date-formatted folder
        if any(parent.name.replace("-", "").isdigit() for parent in image_file.parents):
            return f"Skipping {image_file.name}: already in a date folder"

        creation_date = get_exif_creation_date_pyexiftool(
            str(image_file)
        ) or get_file_creation_date(image_file)

        if not creation_date:
            return f"Skipping {image_file.name}: no valid date found."

        # Format the folder name based on by_month parameter
        folder_format = "%Y-%m" if by_month else "%Y-%m-%d"
        date_folder = target_path / creation_date.strftime(folder_format)

        if not dry_run:
            date_folder.mkdir(parents=True, exist_ok=True)

        # Handle duplicate filenames
        dest_path = date_folder / image_file.name
        if dest_path.exists():
            base = dest_path.stem
            suffix = dest_path.suffix
            counter = 1
            while dest_path.exists():
                dest_path = date_folder / f"{base}_{counter}{suffix}"
                counter += 1

        if dry_run:
            return f"[DRY RUN] Would move {image_file} -> {dest_path}"

        shutil.move(str(image_file), str(dest_path))
        return f"Moved {image_file} -> {dest_path}"
    except Exception as e:
        return f"Error processing {image_file}: {e}"


def organize_images_by_date(
    source_folder, target_folder=None, by_month=False, dry_run=False
):
    """Organizes image and video files into subfolders based on their creation date."""
    source_path = Path(source_folder)
    target_path = Path(target_folder) if target_folder else source_path

    if not source_path.exists() or not source_path.is_dir():
        print("Source folder does not exist or is not a directory.")
        return

    # Update to recursively find all media files using rglob
    media_files = []
    for ext in IMAGE_EXTENSIONS:
        media_files.extend(source_path.rglob(f"*{ext}"))
        media_files.extend(source_path.rglob(f"*{ext.upper()}"))

    if not media_files:
        print("No image or video files found in the source directory.")
        return

    # Modify process args to include the dry_run parameter
    process_args = [(f, target_path, by_month, dry_run) for f in media_files]

    # Use number of CPU cores, but cap it at a reasonable number
    num_processes = min(cpu_count(), 8)

    with Pool(processes=num_processes) as pool:
        # Use imap_unordered for better performance while maintaining progress bar
        for result in tqdm(
            pool.imap_unordered(process_single_image, process_args),
            total=len(media_files),
            desc="Organizing images",
            unit="file",
        ):
            tqdm.write(result)


@click.command()
@click.argument(
    "source",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--target",
    "-t",
    type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    help="Optional target directory (defaults to source directory)",
)
@click.option(
    "--by-month",
    is_flag=True,
    help="Organize files by month (YYYY-MM) instead of by day (YYYY-MM-DD)",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be done without actually moving files",
)
def cli(source: Path, target: Path | None, by_month: bool, dry_run: bool) -> None:
    """Organize images and videos into folders by date."""
    if dry_run:
        click.echo("Running in dry-run mode - no files will be moved")
    organize_images_by_date(source, target, by_month, dry_run)

import os
import json


def clean_duplicates(non_empty_dups: dict, prefix: str):
    for original, duplicates in non_empty_dups.items():
        # Convert numpy string to regular string
        try:
            original_path = os.path.join(prefix, str(original))
            original_size = os.path.getsize(original_path)
        except FileNotFoundError:
            print(f"File not found: {original_path}")
            continue

        # Keep track of all files and their sizes in this group
        files_with_sizes = [(original_path, original_size)]

        # Add duplicates to our list
        for dup_path, _ in duplicates:
            try:
                dup_path = os.path.join(prefix, str(dup_path))
                dup_size = os.path.getsize(dup_path)
                files_with_sizes.append((dup_path, dup_size))
            except FileNotFoundError:
                print(f"File not found: {dup_path}")

        # Sort by file size, largest first
        files_with_sizes.sort(key=lambda x: x[1], reverse=True)

        # Keep the largest file, delete the rest
        largest_file = files_with_sizes[0]
        print(f"Keeping {largest_file[0]} ({largest_file[1]} bytes)")

        for file_path, size in files_with_sizes[1:]:
            print(f"Deleting {file_path} ({size} bytes)")
            try:
                os.remove(file_path)
            except OSError as e:
                print(f"Error deleting {file_path}: {e}")


if __name__ == "__main__":
    non_empty_dups = json.load(open("non_empty_dups.json"))
    clean_duplicates(non_empty_dups, "/mnt/crucial_mx500/darkroom/image/archived/")

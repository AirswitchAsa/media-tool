import click
from media_tool.move import cli as move_cli
from media_tool.dedupe import cli as dedupe_cli


@click.group()
def main():
    """Media Tool - A command line program to organize and deduplicate media files."""
    pass


main.add_command(move_cli, name="move")
main.add_command(dedupe_cli, name="dedupe")

if __name__ == "__main__":
    main()

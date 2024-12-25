import click
import os
import shutil
import toml
from db_utils import process_database, add_connection

__version__ = "0.1.7"

@click.group()
def cli():
    pass

@cli.command()
@click.option('--clean', is_flag=True, help='Clean context directory before processing')
@click.option('--connection', default=None, help='Database connection string or name of connection from configuration file')
@click.option('--debug', is_flag=True, help='Enable debug output')
def generate(clean, connection, debug):
    """Process database and write context files."""
    process_database(connection=connection, clean=clean, debug=debug)

@cli.command()
@click.option('--connection-string', default=None, help='Database connection string')
def add(connection_string):
    """Add a new database connection."""
    add_connection(connection_string)

@cli.command()
def version():
    """Display the version information."""
    click.echo(f'Version {__version__}')

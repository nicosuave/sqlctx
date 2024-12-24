import click
import os
import shutil
import toml
from db_utils import connect_to_database, load_config, get_database_structure, write_context_files

@click.group()
def cli():
    pass

@cli.command()
@click.option('--clean', is_flag=True, help='Clean context directory before processing')
@click.option('--connection', default=None, help='Database connection string or name of connection from configuration file')
@click.option('--debug', is_flag=True, help='Enable debug output')
def generate(clean, connection, debug):
    """Process database and write context files."""
    directory = './sqlctx/'
    config_path = './.sqlctx/config.toml'

    if debug:
        click.echo(f'Debug: Context directory is set to {directory}')

    if not os.path.exists(config_path):
        click.echo('No configuration file found. You need to initialize configuration first. Run `add` command to add a connection.')
        return

    if clean:
        # Clear the target directory
        if os.path.exists(directory):
            if debug:
                click.echo('Debug: Cleaning context directory...')
            shutil.rmtree(directory)

    if debug:
        click.echo('Debug: Establishing database connection...')

    con, connection_name = connect_to_database(connection)
    connection_name = connection_name if connection_name in load_config()['connections'] else "default"

    if debug:
        click.echo(f'Debug: Using connection "{connection_name}"')

    if debug:
        click.echo('Debug: Retrieving database structure...')

    structure = get_database_structure(con)

    if debug:
        click.echo('Debug: Writing context files...')

    write_context_files(con, structure, connection_name)

    if debug:
        click.echo('Debug: Closing database connection...')

    con.close()

@cli.command()
@click.option('--connection-string', default=None, help='Database connection string')
def add(connection_string):
    """Add a new database connection."""
    connection_name = click.prompt('Please enter a connection name', type=str)
    if not connection_string:
        connection_string = click.prompt(
            'Please enter a connection string (e.g., "mysql://user:pass@host/db", "postgresql://user:pass@host/db", or "duckdb:///path/to/db")',
            type=str
        )

    try:
        # Test connection
        con, _ = connect_to_database(connection_string)
        con.close()

        # Write to config
        config_path = './.sqlctx/config.toml'
        if not os.path.exists(config_path):
            config = {'connections': {}}
        else:
            config = load_config()
            if 'connections' not in config or not isinstance(config['connections'], dict):
                config['connections'] = {}

        config['connections'][connection_name] = connection_string

        with open(config_path, 'w') as config_file:
            toml.dump(config, config_file)

        click.echo('Connection added successfully.')

    except Exception as e:
        click.echo(f'Failed to connect: {e}')

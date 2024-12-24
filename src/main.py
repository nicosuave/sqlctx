import click
from cli_commands import cli

if __name__ == "__main__":
    cli()
else:
    from db_utils import connect_to_database, load_config, get_database_structure, write_context_files
    from mcp_server import init_mcp_server
    import os

    con, connection_name = connect_to_database()
    connection_name = connection_name if connection_name in load_config()['connections'] else "default"
    combined_yml_path = os.path.join(os.path.expanduser('~/.sidequery/context'), connection_name, 'combined.yml')
    if not os.path.exists(combined_yml_path):
        structure = get_database_structure(con)
        write_context_files(con, structure, connection_name)
    init_mcp_server(con, combined_yml_path, start=False)

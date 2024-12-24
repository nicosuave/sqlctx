import os
import duckdb
import yaml
import psycopg2
import mysql.connector
from urllib.parse import urlparse
import pandas as pd
import toml

SQLCTX_DIRECTORY = './sqlctx'
CONFIG_DIRECTORY = './.sqlctx'

def load_config():
    config_path = os.path.join(CONFIG_DIRECTORY, 'config.toml')
    if not os.path.exists(config_path):
        # Write default config
        default_config = {
            'connections': {
                'default': f'duckdb://{os.path.join(CONFIG_DIRECTORY, "db.db")}'
            }
        }
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w') as f:
            toml.dump(default_config, f)

    # Load the existing config
    with open(config_path, 'r') as f:
        config = toml.load(f)

    # Replace environment variables in config and throw error if not found
    for conn_name, conn_str in config.get('connections', {}).items():
        expanded_conn_str = os.path.expandvars(conn_str)
        if '$' in expanded_conn_str:
            raise EnvironmentError(f"Environment variable in connection string '{conn_str}' not found for connection '{conn_name}'.")
        config['connections'][conn_name] = expanded_conn_str

    return config

def resolve_connection_string(name_or_string, config):
    connections = config.get('connections', {})
    if name_or_string in connections:
        connection_string = connections[name_or_string]
    else:
        connection_string = name_or_string

    return connection_string

def connect_to_database(name_or_string=None):
    config = load_config()

    if name_or_string is None:
        name_or_string = 'default'
    connection_string = resolve_connection_string(name_or_string, config)
    parsed = urlparse(connection_string)
    if parsed.scheme == 'duckdb':
        db_path = os.path.join(parsed.netloc, parsed.path.lstrip('/')) if parsed.netloc else parsed.path
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            if db_dir.startswith('/'):
                raise ValueError("Cannot create directory at root level")
            os.makedirs(db_dir, exist_ok=True)
        con = duckdb.connect(database=db_path, read_only=False)
        return con, name_or_string
    elif parsed.scheme in ('postgresql', 'postgres'):
        con = psycopg2.connect(
            dbname=parsed.path[1:],
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port
        )
        return con, name_or_string
    elif parsed.scheme == 'mysql':
        con = mysql.connector.connect(
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port,
            database=parsed.path[1:]
        )
        return con, name_or_string
    else:
        raise ValueError(f"Unsupported database scheme: {parsed.scheme}")

def get_database_structure(con):
    tables_query = """
    SELECT
        table_catalog AS database_name,
        table_schema AS schema_name,
        table_name
    FROM information_schema.tables
    WHERE table_type = 'BASE TABLE'
    AND table_schema NOT IN ('information_schema', 'pg_catalog')
    """
    if isinstance(con, duckdb.DuckDBPyConnection):
        tables = con.execute(tables_query).fetchdf().values.tolist()
    elif isinstance(con, psycopg2.extensions.connection):
        with con.cursor() as cursor:
            cursor.execute(tables_query)
            tables = cursor.fetchall()
    elif isinstance(con, mysql.connector.connection_cext.CMySQLConnection):
        cursor = con.cursor()
        cursor.execute(tables_query)
        tables = cursor.fetchall()
        cursor.close()
    else:
        raise TypeError("Unsupported connection type")

    structure = {}
    for db_name, schema_name, table_name in tables:
        # Initialize nested dictionaries
        structure.setdefault(db_name, {}).setdefault(schema_name, {})
        # Get columns for this table
        columns_query = f"""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_catalog = '{db_name}'
          AND table_schema = '{schema_name}'
          AND table_name = '{table_name}'
        """
        if isinstance(con, duckdb.DuckDBPyConnection):
            columns = con.execute(columns_query).fetchdf().values.tolist()
        elif isinstance(con, psycopg2.extensions.connection):
            with con.cursor() as cursor:
                cursor.execute(columns_query)
                columns = cursor.fetchall()
        elif isinstance(con, mysql.connector.connection_cext.CMySQLConnection):
            cursor = con.cursor()
            cursor.execute(columns_query)
            columns = cursor.fetchall()
            cursor.close()
        else:
            raise TypeError("Unsupported connection type")
        structure[db_name][schema_name][table_name] = columns
    return structure

def sample_table(con, db_name, schema_name, table_name, num_samples=3):
    if isinstance(con, duckdb.DuckDBPyConnection):
        qualified_table_name = f'"{db_name}"."{schema_name}"."{table_name}"'
        sample_query = f"SELECT * FROM {qualified_table_name} LIMIT {num_samples}"
        sample_df = con.execute(sample_query).df()
        return sample_df
    elif isinstance(con, psycopg2.extensions.connection):
        qualified_table_name = f'"{schema_name}"."{table_name}"'
        sample_query = f'SELECT * FROM {qualified_table_name} LIMIT {num_samples}'
        with con.cursor() as cursor:
            cursor.execute(sample_query)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
        sample_df = pd.DataFrame(rows, columns=columns)
        return sample_df
    elif isinstance(con, mysql.connector.connection_cext.CMySQLConnection):
        qualified_table_name = f'`{schema_name}`.`{table_name}`'
        sample_query = f"SELECT * FROM {qualified_table_name} LIMIT {num_samples}"
        cursor = con.cursor()
        cursor.execute(sample_query)
        rows = cursor.fetchall()
        columns = cursor.column_names
        cursor.close()
        sample_df = pd.DataFrame(rows, columns=columns)
        return sample_df
    else:
        raise TypeError("Unsupported connection type")

def write_context_files(con, structure, connection_name, directory=None):
    if directory is None:
        directory = os.path.join(SQLCTX_DIRECTORY, connection_name)
    os.makedirs(directory, exist_ok=True)

    # Build overview data
    overview_data = {'databases': []}
    for db_name, schemas_dict in structure.items():
        db_entry = {'name': db_name, 'schemas': []}
        for schema_name, tables_dict in schemas_dict.items():
            schema_entry = {'name': schema_name, 'tables': list(tables_dict.keys())}
            db_entry['schemas'].append(schema_entry)
        overview_data['databases'].append(db_entry)

    # Write overview.yml if the connection name is not a direct connection string
    if connection_name in load_config()['connections']:
        with open(os.path.join(directory, 'overview.yml'), 'w') as f:
            yaml.safe_dump(overview_data, f, default_flow_style=False, sort_keys=False)

    combined_data = []
    for db_name, schemas_dict in structure.items():
        for schema_name, tables_dict in schemas_dict.items():
            for table_name, columns in tables_dict.items():
                # Define the directory path
                path = os.path.join(directory, db_name, schema_name)
                os.makedirs(path, exist_ok=True)
                # Sample the table with 3 records
                sample_df = sample_table(con, db_name, schema_name, table_name, num_samples=3)
                # Prepare sample data
                sample_data_full = sample_df.to_dict(orient='list')
                sample_data = {col: vals[:3] for col, vals in sample_data_full.items()}
                # Define table data
                table_data = {
                    'database': db_name,
                    'schema': schema_name,
                    'table': table_name,
                    'columns': [{cname: ctype} for cname, ctype in columns],
                    'sample data': sample_data,
                }
                # Write table_data to YAML
                table_context_path = os.path.join(path, f"{table_name}.yml")
                with open(table_context_path, 'w') as f:
                    yaml.dump(table_data, f, default_flow_style=False)
                # Add to combined data
                combined_data.append(table_data)

    # Write combined content to a file as proper YAML if connection_name is provided
    if connection_name in load_config()['connections']:
        combined_path = os.path.join(directory, 'combined.yml')
        with open(combined_path, 'w') as f:
            yaml.safe_dump(combined_data, f, default_flow_style=False, sort_keys=False)

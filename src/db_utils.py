import os
import duckdb
from urllib.parse import unquote
from ruamel.yaml import YAML, CommentedMap, CommentedSeq
import psycopg2
import mysql.connector
from urllib.parse import urlparse
import pandas as pd
import toml
import shutil

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

class BaseDatabaseHandler:
    def __init__(self, connection_string, connection_name):
        self.connection_string = connection_string
        self.connection_name = connection_name
        self.con = None

    def connect(self):
        pass

    def close(self):
        if self.con:
            self.con.close()

    def get_database_structure(self):
        pass

    def sample_table(self, db_name, schema_name, table_name, num_samples=3):
        pass

    def write_context_files(self, structure, directory=None):
        if directory is None:
            directory = os.path.join(SQLCTX_DIRECTORY, self.connection_name)
        os.makedirs(directory, exist_ok=True)

        yaml = YAML()

        # Build overview data
        overview_data = {'databases': []}
        for db_name, schemas_dict in structure.items():
            db_entry = {'name': db_name, 'schemas': []}
            for schema_name, tables_dict in schemas_dict.items():
                schema_entry = {'name': schema_name, 'tables': list(tables_dict.keys())}
                db_entry['schemas'].append(schema_entry)
            overview_data['databases'].append(db_entry)

        # Write overview.yml if the connection name is not a direct connection string
        if self.connection_name in load_config()['connections']:
            with open(os.path.join(directory, 'overview.yml'), 'w') as f:
                yaml.dump(overview_data, f)

        combined_data = []
        for db_name, schemas_dict in structure.items():
            for schema_name, tables_dict in schemas_dict.items():
                for table_name, table_info in tables_dict.items():
                    columns_info = table_info['columns']
                    table_comment = table_info['table_comment']
                    # Define the directory path
                    path = os.path.join(directory, db_name, schema_name)
                    os.makedirs(path, exist_ok=True)
                    # Sample the table with 3 records
                    sample_df = self.sample_table(db_name, schema_name, table_name, num_samples=3)
                    # Prepare sample data
                    sample_data_full = sample_df.to_dict(orient='list')
                    sample_data = {col: vals[:3] for col, vals in sample_data_full.items()}

                    # Define table data using CommentedMap
                    table_data = CommentedMap()
                    table_data['database'] = db_name
                    table_data['schema'] = schema_name
                    table_data['table'] = table_name

                    if table_comment:
                        table_data.yaml_add_eol_comment(table_comment, 'table')

                    # Add 'sample data' before 'columns'
                    table_data['sample data'] = sample_data
                    # Build columns
                    columns_seq = CommentedSeq()
                    for idx, (col_name, data_type, col_comment) in enumerate(columns_info):
                        col_entry = CommentedMap()
                        col_entry[col_name] = data_type
                        if col_comment:
                            col_entry.yaml_add_eol_comment(col_comment, col_name)
                        columns_seq.append(col_entry)

                    table_data['columns'] = columns_seq

                    # Write table_data to YAML
                    table_context_path = os.path.join(path, f"{table_name}.yml")
                    with open(table_context_path, 'w') as f:
                        yaml.dump(table_data, f)

                    # Add to combined data
                    combined_data.append(table_data)

        # Write combined content to a file as proper YAML if connection_name is provided
        if self.connection_name in load_config()['connections']:
            combined_path = os.path.join(directory, 'combined.yml')
            with open(combined_path, 'w') as f:
                yaml.dump(combined_data, f)

class DuckDBHandler(BaseDatabaseHandler):
    def connect(self):
        parsed = urlparse(self.connection_string)
        db_path = os.path.join(parsed.netloc, parsed.path.lstrip('/')) if parsed.netloc else parsed.path
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            if db_dir.startswith('/'):
                raise ValueError("Cannot create directory at root level")
            os.makedirs(db_dir, exist_ok=True)
        self.con = duckdb.connect(database=db_path, read_only=False)

    def get_database_structure(self):
        structure = {}
        # Tables query
        tables_query = """
        SELECT
            table_catalog AS database_name,
            table_schema AS schema_name,
            table_name,
            '' AS table_comment  -- DuckDB does not support table comments
        FROM information_schema.tables
        WHERE table_type = 'BASE TABLE'
        AND table_schema NOT IN ('information_schema', 'pg_catalog')
        """
        tables = self.con.execute(tables_query).fetchdf().values.tolist()
        # Process tables
        for db_name, schema_name, table_name, table_comment in tables:
            # Initialize nested dictionaries
            structure.setdefault(db_name, {}).setdefault(schema_name, {})
            # Get columns for this table
            columns_query = f"""
            SELECT
                column_name,
                data_type,
                '' AS column_comment  -- DuckDB does not support column comments
            FROM information_schema.columns
            WHERE table_catalog = '{db_name}'
              AND table_schema = '{schema_name}'
              AND table_name = '{table_name}'
            """
            columns = self.con.execute(columns_query).fetchdf().values.tolist()
            structure[db_name][schema_name][table_name] = {
                'columns': columns,
                'table_comment': table_comment
            }
        return structure

    def sample_table(self, db_name, schema_name, table_name, num_samples=3):
        qualified_table_name = f'"{db_name}"."{schema_name}"."{table_name}"'
        sample_query = f"SELECT * FROM {qualified_table_name} LIMIT {num_samples}"
        sample_df = self.con.execute(sample_query).df()
        return sample_df

class PostgresHandler(BaseDatabaseHandler):
    def connect(self):
        parsed = urlparse(self.connection_string)
        self.con = psycopg2.connect(
            dbname=parsed.path[1:],
            user=parsed.username,
            password=parsed.password,
            host=parsed.hostname,
            port=parsed.port or 5432
        )

    def get_database_structure(self):
        structure = {}
        with self.con.cursor() as cursor:
            # Tables query
            tables_query = """
            SELECT
                n.nspname AS schema_name,
                c.relname AS table_name,
                obj_description(c.oid) AS table_comment
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relkind = 'r' -- Only tables
            AND n.nspname NOT IN ('pg_catalog', 'information_schema')
            """
            cursor.execute(tables_query)
            tables = cursor.fetchall()
            for schema_name, table_name, table_comment in tables:
                db_name = self.con.get_dsn_parameters()['dbname']
                # Initialize nested dictionaries
                structure.setdefault(db_name, {}).setdefault(schema_name, {})
                # Get columns for this table
                columns_query = f"""
                SELECT
                    a.attname AS column_name,
                    pg_catalog.format_type(a.atttypid, a.atttypmod) AS data_type,
                    col_description(a.attrelid, a.attnum) AS column_comment
                FROM pg_attribute a
                WHERE a.attrelid = '{schema_name}.{table_name}'::regclass
                  AND a.attnum > 0
                  AND NOT a.attisdropped
                ORDER BY a.attnum
                """
                cursor.execute(columns_query)
                columns = cursor.fetchall()
                structure[db_name][schema_name][table_name] = {
                    'columns': columns,
                    'table_comment': table_comment
                }
        return structure

    def sample_table(self, db_name, schema_name, table_name, num_samples=3):
        qualified_table_name = f'"{schema_name}"."{table_name}"'
        sample_query = f'SELECT * FROM {qualified_table_name} LIMIT {num_samples}'
        with self.con.cursor() as cursor:
            cursor.execute(sample_query)
            rows = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description]
        sample_df = pd.DataFrame(rows, columns=columns)
        return sample_df

class MySQLHandler(BaseDatabaseHandler):
    def connect(self):
        parsed = urlparse(self.connection_string)
        self.con = mysql.connector.connect(
            user=parsed.username,
            password=unquote(parsed.password),
            host=parsed.hostname,
            port=parsed.port or 3306,
            database=parsed.path[1:]
        )

    def get_database_structure(self):
        structure = {}
        cursor = self.con.cursor()
        # Tables query
        tables_query = """
        SELECT
            TABLE_SCHEMA AS schema_name,
            TABLE_NAME AS table_name,
            TABLE_COMMENT AS table_comment
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_TYPE = 'BASE TABLE'
        AND TABLE_SCHEMA NOT IN ('information_schema', 'performance_schema', 'mysql', 'sys')
        """
        cursor.execute(tables_query)
        tables = cursor.fetchall()
        for schema_name, table_name, table_comment in tables:
            db_name = self.con.database
            # Initialize nested dictionaries
            structure.setdefault(db_name, {}).setdefault(schema_name, {})
            # Get columns for this table
            columns_query = f"""
            SELECT
                COLUMN_NAME AS column_name,
                COLUMN_TYPE AS data_type,
                COLUMN_COMMENT AS column_comment
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = '{schema_name}'
              AND TABLE_NAME = '{table_name}'
            ORDER BY ORDINAL_POSITION
            """
            cursor.execute(columns_query)
            columns = cursor.fetchall()
            structure[db_name][schema_name][table_name] = {
                'columns': columns,
                'table_comment': table_comment
            }
        cursor.close()
        return structure

    def sample_table(self, db_name, schema_name, table_name, num_samples=3):
        qualified_table_name = f'`{schema_name}`.`{table_name}`'
        sample_query = f"SELECT * FROM {qualified_table_name} LIMIT {num_samples}"
        cursor = self.con.cursor()
        cursor.execute(sample_query)
        rows = cursor.fetchall()
        columns = cursor.column_names
        cursor.close()
        sample_df = pd.DataFrame(rows, columns=columns)
        return sample_df

def get_database_handler(name_or_string=None):
    config = load_config()

    if name_or_string is None:
        name_or_string = 'default'
    connection_string = resolve_connection_string(name_or_string, config)
    parsed = urlparse(connection_string)
    connection_name = name_or_string  # Can be a name or connection string

    if parsed.scheme == 'duckdb':
        handler = DuckDBHandler(connection_string, connection_name)
    elif parsed.scheme in ('postgresql', 'postgres'):
        handler = PostgresHandler(connection_string, connection_name)
    elif parsed.scheme == 'mysql':
        handler = MySQLHandler(connection_string, connection_name)
    else:
        raise ValueError(f"Unsupported database scheme: {parsed.scheme}")

    handler.connect()
    return handler

def process_database(connection=None, clean=False, debug=False):
    handler = get_database_handler(connection)
    directory = os.path.join(SQLCTX_DIRECTORY, handler.connection_name)

    if debug:
        print(f'Debug: Context directory is set to {directory}')

    if clean:
        # Clear the target directory
        if os.path.exists(directory):
            if debug:
                print('Debug: Cleaning context directory...')
            shutil.rmtree(directory)

    if debug:
        print('Debug: Retrieving database structure...')

    structure = handler.get_database_structure()

    if debug:
        print('Debug: Writing context files...')

    handler.write_context_files(structure)

    if debug:
        print('Debug: Closing database connection...')

    handler.close()

def add_connection(connection_string=None):
    connection_name = input('Please enter a connection name: ')
    if not connection_string:
        connection_string = input(
            'Please enter a connection string (e.g., "mysql://user:pass@host/db", "postgresql://user:pass@host/db", or "duckdb:///path/to/db"): '
        )

    try:
        # Test connection
        handler = get_database_handler(connection_string)
        handler.close()

        # Write to config
        config_path = os.path.join(CONFIG_DIRECTORY, 'config.toml')
        if not os.path.exists(config_path):
            config = {'connections': {}}
        else:
            config = load_config()
            if 'connections' not in config or not isinstance(config['connections'], dict):
                config['connections'] = {}

        config['connections'][connection_name] = connection_string

        with open(config_path, 'w') as config_file:
            toml.dump(config, config_file)

        print('Connection added successfully.')

    except Exception as e:
        print(f'Failed to connect: {e}')

import duckdb
from click.testing import CliRunner
from sqlctx.cli_commands import cli
import os
import psycopg2
import mysql.connector

def test_add_postgres_connection():
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli,
                               ['add', '--connection-string', 'postgresql://test_user:test_password@localhost/test_db', '--name', 'postgres_connection'])

        assert result.exit_code == 0, f"CLI exited with {result.exit_code}, output: {result.output}"
        assert 'Connection added successfully.' in result.output

        with open(".sqlctx/config.toml", "r") as f:
            config_content = f.read()
        assert 'postgres_connection = "postgresql://test_user:test_password@localhost/test_db"' in config_content, f"Config file content:\n{config_content}"

def test_add_mysql_connection():
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli,
                               ['add', '--connection-string', 'mysql://test_user:test_password@localhost/test_db', '--name', 'mysql_connection'])

        assert result.exit_code == 0, f"CLI exited with {result.exit_code}, output: {result.output}"
        assert 'Connection added successfully.' in result.output

        with open(".sqlctx/config.toml", "r") as f:
            config_content = f.read()
        assert 'mysql_connection = "mysql://test_user:test_password@localhost/test_db"' in config_content, f"Config file content:\n{config_content}"

def test_add_duckdb_connection():
    runner = CliRunner()

    db_path = "./db.duckdb"
    duckdb.connect(db_path)
    with runner.isolated_filesystem():
        result = runner.invoke(cli,
                               ['add', '--connection-string', f'duckdb://{db_path}', '--name', 'duckdb_connection'])

        assert result.exit_code == 0, f"CLI exited with {result.exit_code}, output: {result.output}"
        assert 'Connection added successfully.' in result.output

        with open(".sqlctx/config.toml", "r") as f:
            config_content = f.read()
        assert f'duckdb_connection = "duckdb://{db_path}"' in config_content, f"Config file content:\n{config_content}"

def test_generate_postgres():
    runner = CliRunner()

    with runner.isolated_filesystem():
        os.makedirs(".sqlctx", exist_ok=True)  # Ensure the directory exists
        with open(".sqlctx/config.toml", "w") as f:
            f.write('[connections]\npostgres_connection = "postgresql://test_user:test_password@localhost/test_db"\n')

        # Connect to the PostgreSQL database
        conn = psycopg2.connect("dbname=test_db user=test_user password=test_password host=localhost")
        cursor = conn.cursor()

        cursor.execute('CREATE TABLE if not exists test_table (id SERIAL PRIMARY KEY, name VARCHAR(50));')
        cursor.execute("INSERT INTO test_table (name) VALUES ('test_name');")
        conn.commit()
        cursor.close()
        conn.close()

        result = runner.invoke(cli, ['generate', '--connection', 'postgres_connection', '--clean'])

        assert result.exit_code == 0
        assert os.path.exists("sqlctx/postgres_connection/combined.yml"), "combined.yml file does not exist"
        assert os.path.exists("sqlctx/postgres_connection/overview.yml"), "overview.yml file does not exist"
        assert os.path.exists("sqlctx/postgres_connection/test_db/public/test_table.yml"), "test_table.yml file does not exist"

def test_generate_mysql():
    runner = CliRunner()
    with runner.isolated_filesystem():
        os.makedirs(".sqlctx", exist_ok=True)
        with open(".sqlctx/config.toml", "w") as f:
            f.write('[connections]\nmysql_connection = "mysql://test_user:test_password@localhost/test_db"\n')


        # Establish a connection to the MySQL database
        connection = mysql.connector.connect(
            user='test_user',
            password='test_password',
            host='localhost',
            database='test_db'
        )

        cursor = connection.cursor()

        # Create a table and insert data
        cursor.execute('CREATE TABLE IF NOT EXISTS test_table (id INT AUTO_INCREMENT PRIMARY KEY, name VARCHAR(50));')
        cursor.execute("INSERT INTO test_table (name) VALUES ('test_name');")
        connection.commit()

        cursor.close()
        connection.close()

        result = runner.invoke(cli, ['generate', '--connection', 'mysql_connection', '--clean'])
        assert result.exit_code == 0
        assert os.path.exists("sqlctx/mysql_connection/combined.yml"), "combined.yml file does not exist"
        assert os.path.exists("sqlctx/mysql_connection/overview.yml"), "overview.yml file does not exist"
        assert os.path.exists("sqlctx/mysql_connection/test_db/test_db/test_table.yml"), "test_table.yml file does not exist"

def test_generate_duckdb():
    runner = CliRunner()

    with runner.isolated_filesystem():
        os.makedirs(".sqlctx", exist_ok=True)
        with open(".sqlctx/config.toml", "w") as f:
            f.write('[connections]\nduckdb_connection = "duckdb://./mock/db.duckdb"\n')

        os.makedirs("./mock/db", exist_ok=True)

        # Connect to the DuckDB and create tables
        conn = duckdb.connect('./mock/db.duckdb')
        cursor = conn.cursor()

        cursor.execute('CREATE TABLE test_table (id INTEGER, name VARCHAR);')
        cursor.execute('INSERT INTO test_table VALUES (1, \'test_name\');')

        result = runner.invoke(cli, ['generate', '--connection', 'duckdb_connection', '--clean'])

        assert result.exit_code == 0
        print(result.output)

        assert os.path.exists("sqlctx/duckdb_connection/combined.yml"), "combined.yml file does not exist"
        assert os.path.exists("sqlctx/duckdb_connection/overview.yml"), "overview.yml file does not exist"
        assert os.path.exists("sqlctx/duckdb_connection/db/main/test_table.yml"), "test_table.yml file does not exist"

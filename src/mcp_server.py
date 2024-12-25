from fastmcp import FastMCP
import duckdb
import psycopg2
import mysql.connector
import pandas as pd
import yaml
import duckdb
import os
from db_utils import connect_to_database, load_config

# Initialize the FastMCP instance as a global variable
mcp = FastMCP("Database Explorer")

def init_mcp_server(con, combined_yml_path, start=True):
    @mcp.resource("schema://main")
    def get_schema() -> str:
        """Provide the database schema as a resource"""
        with open(combined_yml_path, 'r') as f:
            combined_schema = f.read()
        return combined_schema

    @mcp.tool()
    def query_data(sql: str) -> str:
        """Execute SQL queries safely"""
        try:
            if isinstance(con, duckdb.DuckDBPyConnection):
                result = con.execute(sql).fetchdf()
                return result.to_string()
            elif isinstance(con, psycopg2.extensions.connection):
                with con.cursor() as cursor:
                    cursor.execute(sql)
                    rows = cursor.fetchall()
                    return '\n'.join(str(row) for row in rows)
            elif isinstance(con, mysql.connector.connection_cext.CMySQLConnection):
                cursor = con.cursor()
                cursor.execute(sql)
                rows = cursor.fetchall()
                cursor.close()
                return '\n'.join(str(row) for row in rows)
            else:
                return "Unsupported connection type."
        except Exception as e:
            return f"Error: {str(e)}"

    print("MCP server is starting...")

    if start:
        mcp.run()

def setup_and_run_mcp_server(connection=None):
    con, connection_name = connect_to_database(connection)
    connection_name = connection_name if connection_name in load_config()['connections'] else "default"
    directory = os.path.expanduser('./context/')
    combined_yml_path = os.path.join(directory, connection_name, 'combined.yml')
    init_mcp_server(con, combined_yml_path, start=False)

setup_and_run_mcp_server()

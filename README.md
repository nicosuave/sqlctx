# sqlctx

`sqlctx` or (SQLContext) is a tool for generating LLM context from database tables. It is targeted at data practioners as a force multiplier, codifying the process of providing table schema to LLMs inside of AI-enabled code editors.

Rather than existing as an editor extension, SQLContext outputs context about your database to a directory (`./sqlctx/{schema_name}/{database_name}/{table_name}.yml`) on a per table basis so that you can include them with any LLM-enabled editor by mentioning the file for that database table. Alternatively, there's a `combined.yml` file that includes output from all the columns from all the tables for long-context LLMs.

Inside each yml file is metadata like the table, database, & schema names, as well as sample values for each column. If you have set column or table comments using tools like DBT or SQLMesh, they will also be extracted.

SQLContext pairs well with:

- Visual Studio Code
- Cursor
- Zed
- Windsurf

SQLContext supports databases that use the following protocols:

- DuckDB
- Postgres
- MySQL

## Getting Started

Start by installing either `uv` or `pipx` to run python CLIs without installing to system packages.

### Configuration

SQLContext can be run on demand or configured. To configure for a given directory, run the following to generate a config file. You will need your database connection information handy.

`uvx sqlctx add` or if you're using pipx `pipx sqlctx add`

A config file will be written to `.sqlctx/config.toml`. You can embed environment variables directly in the toml like `${ENV_VAR}` and they will be replaced if the variable has been set.

## Generating Context

You can generate context with the `uvx sqlctx generate` command. It will be written to the relative directory `./sqlctx`.

It is recommended that you check this directory into your repository and _not_ gitignore, since your editor likely does not treat gitignored files the same as regular project files, and this will break the expected editor workflow.

## Consuming Context

Since most AI editors allow mentioning files, SQLContext relies on this. When writing a new query, simply "mention" a table to include the schema and a few sample records in the context of your chat.

For example, if I'm writing a query calculting ARPU, I might choose to mention my `sessions` table and `revenue` table, since I know these are relevant.

1. Visual Studio Code - `CMD + /` from any copilot input to include any project file
2. Zed - `CMD + /` from the context pane to include any project file
3. Cursor — `@`-mention the relevant tables in chat, composer, or inline edit
4. Windsurf - `@`-mention the relevant table from the Cascade UI

Many editors also have a RAG-search that surfaces relevant files without explicit mention, but explicitly mentioning relevant tables tends to lead to the highest quality generations.

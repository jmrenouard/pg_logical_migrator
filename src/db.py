"""
db.py — PostgreSQL interaction layer.

Provides the :class:`PostgresClient` for executing queries/scripts against
a PostgreSQL instance via ``psycopg`` (v3), along with helper functions for
shell command execution (``pg_dump``/``psql``) and schema resolution.

Module-level flag ``VERBOSE`` controls diagnostic output (toggled by CLI).
"""

import psycopg
import sys
from contextlib import contextmanager
import os
import stat
import tempfile

# Module-level verbose flag — toggled by CLI --verbose / -v
VERBOSE = False


def _verbose_print(label: str, content, file=sys.stderr):
    """Print verbose diagnostic information when VERBOSE is True."""
    if not VERBOSE:
        return
    prefix = f"\033[36m[VERBOSE:{label}]\033[0m"
    if isinstance(content, list):
        print(f"{prefix}", file=file)
        for item in content:
            print(f"  {item}", file=file)
    else:
        print(f"{prefix} {content}", file=file)


class PostgresClient:
    def __init__(self, conn_uri, label="DB"):
        self.conn_uri = conn_uri
        self.label = label

    @contextmanager
    def get_conn(self, autocommit=False) -> psycopg.Connection:
        import psycopg.rows
        conn = psycopg.connect(
            self.conn_uri,
            row_factory=psycopg.rows.dict_row,
            autocommit=autocommit)
        try:
            yield conn
        finally:
            conn.close()

    def execute_query(self, query, params=None, fetch=True, autocommit=False):
        _verbose_print(f"{self.label}:SQL", query.strip())
        if params:
            _verbose_print(f"{self.label}:PARAMS", params)
        try:
            with self.get_conn(autocommit=autocommit) as conn:
                cur = conn.execute(query, params)
                if fetch:
                    result = cur.fetchall()
                    _verbose_print(f"{self.label}:RESULT", result if len(
                        result) <= 20 else f"{len(result)} rows returned")
                    return result
                _verbose_print(f"{self.label}:RESULT",
                               "(no fetch – statement executed)")
        except Exception as e:
            _verbose_print(f"{self.label}:ERROR", str(e))
            raise

    def execute_script(self, script, autocommit=False):
        _verbose_print(f"{self.label}:SCRIPT", script.strip())
        try:
            with self.get_conn(autocommit=autocommit) as conn:
                conn.execute(script)
                if not autocommit:
                    conn.commit()
                _verbose_print(f"{self.label}:RESULT",
                               "(script executed successfully)")
        except Exception as e:
            _verbose_print(f"{self.label}:ERROR", str(e))
            raise



@contextmanager
def pgpass_context(source_conn, dest_conn=None):
    """
    Temporarily sets up PGPASSFILE pointing to a secure temp file
    containing passwords for source and (optionally) destination.
    """
    fd, path = tempfile.mkstemp(prefix="pg_logical_migrator_")
    try:
        with os.fdopen(fd, 'w') as f:
            for conn in [c for c in (source_conn, dest_conn) if c]:
                host = conn.get('host', '*')
                port = conn.get('port', '*')
                user = conn.get('user', '*')
                pwd = conn.get('password', '')
                if pwd:
                    f.write(f"{host}:{port}:*:{user}:{pwd}\n")
                    
        original_pgpassfile = os.environ.get('PGPASSFILE')
        os.environ['PGPASSFILE'] = path
        yield
    finally:
        if original_pgpassfile is not None:
            os.environ['PGPASSFILE'] = original_pgpassfile
        else:
            os.environ.pop('PGPASSFILE', None)
        try:
            os.remove(path)
        except Exception:
            pass

def pretty_size(bytes_size):
    """Convert bytes to human readable format."""
    if bytes_size is None:
        return "0 B"
    for unit in ['B', 'kB', 'MB', 'GB', 'TB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:3.1f} {unit}".replace(".0 ", " ")
        bytes_size /= 1024.0
    return f"{bytes_size:3.1f} PB"


def execute_shell_command(command, log_cmd=None):
    import subprocess
    import logging
    display_cmd = log_cmd or command
    prefix = "" if display_cmd.strip().startswith("[") else "[LOCAL] "
    _verbose_print("CMD", display_cmd)
    try:
        logging.info(f"{prefix}Executing: {display_cmd}")
        result = subprocess.run(
            command,
            shell=True,
            check=True,
            capture_output=True,
            text=True)
        _verbose_print("STDOUT", result.stdout.strip()
                       if result.stdout.strip() else "(empty)")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        _verbose_print("ERROR", e.stderr.strip() if e.stderr else str(e))
        logging.error(f"{prefix}Command failed: {e.stderr}")
        return False, e.stderr


def resolve_target_schemas(client, config, db_name=None):
    """
    Returns actual schema names from the database, excluding system 
    and known extension schemas (e.g. postgis) when requested schemas is ['all'].
    """
    schemas = config.get_target_schemas(db_name)
    if schemas != ['all']:
        return schemas
        
    query = """
    SELECT schema_name 
    FROM information_schema.schemata 
    WHERE schema_name NOT IN (
        'information_schema', 'pg_catalog', 'postgis', 
        'topology', 'tiger', 'tiger_data', 'pg_stat_statements'
    )
    AND schema_name NOT LIKE 'pg_temp_%' 
    AND schema_name NOT LIKE 'pg_toast%'
    """
    try:
        res = client.execute_query(query)
        if isinstance(res, list):
            resolved = [r['schema_name'] for r in res]
            if resolved:
                return resolved
        return ['all']
    except Exception as e:
        import logging
        logging.error(f"Failed to resolve schemas: {e}")
        return ['all']

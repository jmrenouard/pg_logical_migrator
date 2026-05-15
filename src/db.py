"""
db.py — PostgreSQL interaction layer.

Provides the :class:`PostgresClient` for executing queries/scripts against
a PostgreSQL instance via ``psycopg`` (v3), along with helper functions for
shell command execution (``pg_dump``/``psql``) and schema resolution.

Module-level flag ``VERBOSE`` controls diagnostic output (toggled by CLI).
"""

import logging
import os
import re
import shlex
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from typing import Optional

import psycopg
import psycopg.rows


# ---------------------------------------------------------------------------
#  Security utilities
# ---------------------------------------------------------------------------

# Whitelist pattern for PostgreSQL identifiers (schemas, tables, roles,
# publication/subscription names, etc.).  Rejects anything that contains
# characters that could be used for SQL injection.
_SAFE_IDENT_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_$]*$')


def sanitize_identifier(name: str) -> str:
    """Return *name* quoted as a SQL identifier if it is safe.

    Raises ``ValueError`` if *name* contains characters outside the
    PostgreSQL identifier character set (letters, digits, underscore, $).
    This is a defence-in-depth measure for DDL statements that cannot use
    parameterised queries (e.g. ``CREATE PUBLICATION``, ``ALTER SUBSCRIPTION``).
    """
    if not name or not _SAFE_IDENT_RE.match(name):
        raise ValueError(
            f"Unsafe SQL identifier rejected: {name!r}. "
            "Only letters, digits, underscores and $ are allowed."
        )
    return f'"{name}"'


def redact_conninfo(conninfo: str) -> str:
    """Remove passwords from a libpq connection string or URI.

    Handles both key=value format and postgresql:// URIs.
    """
    # key=value format: password=secret  →  password=***
    redacted = re.sub(
        r'(password\s*=\s*)(\S+)',
        r'\1***',
        conninfo,
        flags=re.IGNORECASE,
    )
    # URI format: postgresql://user:secret@host  →  postgresql://user:***@host
    redacted = re.sub(
        r'(://[^:]+:)([^@]+)(@)',
        r'\1***\3',
        redacted,
    )
    return redacted

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
        self._conn_txn = None
        self._conn_auto = None

    def close(self):
        """Close any cached connections."""
        if self._conn_txn and not self._conn_txn.closed:
            self._conn_txn.close()
        if self._conn_auto and not self._conn_auto.closed:
            self._conn_auto.close()

    def _create_conn(self, autocommit: bool) -> psycopg.Connection:
        return psycopg.connect(
            self.conn_uri,
            row_factory=psycopg.rows.dict_row,  # type: ignore
            autocommit=autocommit,
            connect_timeout=10,
            options="-c statement_timeout=300000"
        )

    @contextmanager
    def get_conn(self, autocommit=False):
        if autocommit:
            if self._conn_auto is None or self._conn_auto.closed:
                self._conn_auto = self._create_conn(autocommit=True)
            conn = self._conn_auto
            try:
                yield conn
            finally:
                pass  # Keep autocommit connection open for reuse
        else:
            if self._conn_txn is None or self._conn_txn.closed:
                self._conn_txn = self._create_conn(autocommit=False)
            conn = self._conn_txn
            try:
                yield conn
            finally:
                if not conn.closed:
                    conn.rollback()  # Clean up any uncommitted transaction state

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
                if not autocommit:
                    conn.commit()
                _verbose_print(f"{self.label}:RESULT",
                               "(no fetch – statement executed)")
                return getattr(cur, 'rowcount', None)
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
    os.fchmod(fd, 0o600)
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


def execute_shell_command(command, log_cmd: Optional[str] = None):
    """Execute a shell command safely with shell=False.

    *command* may be a list of arguments (preferred) or a string.
    If a string is passed it is split with :func:`shlex.split`.
    """
    if isinstance(command, str):
        cmd_list = shlex.split(command)
    else:
        cmd_list = list(command)

    display_cmd = log_cmd or (command if isinstance(command, str) else " ".join(command))
    prefix = "" if str(display_cmd).strip().startswith("[") else "[LOCAL] "
    _verbose_print("CMD", display_cmd)
    try:
        logging.info(f"{prefix}Executing: {display_cmd}")
        result = subprocess.run(
            cmd_list,
            shell=False,
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


def pipe_shell_commands(producer_args: list, consumer_args: list,
                        log_cmd: Optional[str] = None):
    """Run *producer_args* | *consumer_args* safely without ``shell=True``.

    Both arguments must be lists (no string interpolation).
    Returns ``(success: bool, combined_output: str)``.
    """
    display_cmd = log_cmd or f"{' '.join(producer_args)} | {' '.join(consumer_args)}"
    prefix = "" if display_cmd.strip().startswith("[") else "[LOCAL] "
    _verbose_print("PIPE", display_cmd)
    try:
        logging.info(f"{prefix}Executing: {display_cmd}")
        p1 = subprocess.Popen(producer_args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        p2 = subprocess.Popen(consumer_args, stdin=p1.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if p1.stdout:
            p1.stdout.close()  # Allow p1 to receive SIGPIPE if p2 exits

        stdout, stderr = p2.communicate()
        p1.wait()

        # pg_dump|psql: psql may report non-fatal errors (e.g. "already exists")
        # so we check both exit codes
        if p1.returncode != 0:
            p1_stderr = p1.stderr.read() if p1.stderr else ""
            _verbose_print("ERROR", f"Producer failed (rc={p1.returncode}): {p1_stderr}")
            logging.error(f"{prefix}Producer failed: {p1_stderr}")
            return False, p1_stderr
        if p2.returncode != 0:
            _verbose_print("ERROR", stderr.strip() if stderr else "(empty)")
            logging.error(f"{prefix}Consumer failed: {stderr}")
            return False, stderr

        _verbose_print("STDOUT", stdout.strip() if stdout.strip() else "(empty)")
        return True, stdout
    except Exception as e:
        _verbose_print("ERROR", str(e))
        logging.error(f"{prefix}Pipe command failed: {e}")
        return False, str(e)


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
        logging.error(f"Failed to resolve schemas: {e}")
        return ['all']

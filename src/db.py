import psycopg
import sys
from contextlib import contextmanager

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
        conn = psycopg.connect(self.conn_uri, row_factory=psycopg.rows.dict_row, autocommit=autocommit)
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
                    _verbose_print(f"{self.label}:RESULT", result if len(result) <= 20 else f"{len(result)} rows returned")
                    return result
                _verbose_print(f"{self.label}:RESULT", "(no fetch – statement executed)")
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
                _verbose_print(f"{self.label}:RESULT", "(script executed successfully)")
        except Exception as e:
            _verbose_print(f"{self.label}:ERROR", str(e))
            raise

def execute_shell_command(command, log_cmd=None):
    import subprocess
    import logging
    display_cmd = log_cmd or command
    _verbose_print("CMD", display_cmd)
    try:
        logging.info(f"Executing: {display_cmd}")
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        _verbose_print("STDOUT", result.stdout.strip() if result.stdout.strip() else "(empty)")
        return True, result.stdout
    except subprocess.CalledProcessError as e:
        _verbose_print("ERROR", e.stderr.strip() if e.stderr else str(e))
        logging.error(f"Command failed: {e.stderr}")
        return False, e.stderr

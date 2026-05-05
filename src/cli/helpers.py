import datetime
import logging
import os
import sys
import textwrap

from src.config import Config
from src.db import PostgresClient


def setup_logging(level: str = "INFO", log_file: str = None):
    """Configure root logger with console + optional file handler."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    handlers = []
    handlers.append(logging.StreamHandler(sys.stderr))

        
    if log_file:
        os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)
        handlers.append(logging.FileHandler(log_file))

    for h in logging.root.handlers[:]:
        logging.root.removeHandler(h)

    logging.basicConfig(
        level=numeric_level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=handlers,
        force=True,
    )


def setup_results_dir(base: str = None) -> str:
    """Create and return a timestamped results directory."""
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    if base:
        results_dir = base
    else:
        results_dir = os.path.join("RESULTS", timestamp)
    os.makedirs(results_dir, exist_ok=True)
    return results_dir


def build_clients(config: Config):
    """Return (source_client, dest_client) from a Config object."""
    sc = PostgresClient(config.get_source_conn(), label="SOURCE")
    dc = PostgresClient(config.get_dest_conn(), label="DESTINATION")
    return sc, dc


def print_status(success: bool, message: str):
    """Pretty-print a step result to stdout."""
    tag = "\033[32m[OK]\033[0m" if success else "\033[31m[FAIL]\033[0m"
    print(f"  {tag}  {message}")


def print_table(headers: list, rows: list):
    """Print a simple ASCII table to stdout."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))

    fmt = "  ".join(f"{{:<{w}}}" for w in col_widths)
    print()
    print(fmt.format(*headers))
    print(fmt.format(*["-" * w for w in col_widths]))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))
    print()


def print_verbose_execution(args, cmds, outs=None):
    """If verbose is enabled, print commands and outputs to stdout. Also prints structured statuses."""
    outs = outs or []
    
    # Always print structured statuses
    printed_status = False
    for out in outs:
        out_str = str(out)
        if out_str.startswith("  - "):
            if not printed_status:
                print()
                printed_status = True
            print(out_str)
            
    if not getattr(args, "verbose", False) or not cmds:
        return
        
    print("\n  [VERBOSE] Executed Commands and Results:")
    for i, c in enumerate(cmds):
        print(f"    CMD: {str(c).strip()}")
        if i < len(outs) and outs[i]:
            out_str = str(outs[i]).strip()
            # Skip if we already printed this as a structured status
            if str(outs[i]).startswith("  - "):
                continue
            lines = out_str.split("\n")
            if len(lines) > 10:
                print(f"    OUT: {lines[0]}")
                print(f"         ... ({len(lines) - 2} lines hidden) ...")
                print(f"         {lines[-1]}")
            else:
                for idx, line in enumerate(lines):
                    prefix = "    OUT: " if idx == 0 else "         "
                    print(f"{prefix}{line}")
    print()


def generate_sample_config(path: str):
    """Write a sample config_migrator.ini to *path*."""
    content = textwrap.dedent("""\
        [source]
        host = localhost
        port = 5432
        user = postgres
        password = secret
        database = source_db

        [destination]
        host = localhost
        port = 5433
        user = postgres
        password = secret
        database = dest_db

        [replication]
        publication_name = migrator_pub
        subscription_name = migrator_sub
        target_schema = public
        loglevel = INFO
        log_file = pg_migrator.log
    """)
    with open(path, "w") as fh:
        fh.write(content)
    print(f"Sample configuration written to: {path}")

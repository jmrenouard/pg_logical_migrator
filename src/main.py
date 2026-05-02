import argparse
import os
import datetime

from src.tui import MigratorApp


def setup_results_dir():
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = os.path.join("RESULTS", timestamp)
    os.makedirs(results_dir, exist_ok=True)
    return results_dir


def main():
    parser = argparse.ArgumentParser(description="PostgreSQL Logical Migrator")
    parser.add_argument(
        "--config",
        default="config_migrator.ini",
        help="Path to config .ini file")
    args = parser.parse_args()

    app = MigratorApp(args.config)
    app.run()


if __name__ == "__main__":
    main()

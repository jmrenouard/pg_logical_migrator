import re
import os

with open("src/migrator.py", "r") as f:
    content = f.read()

# Define the mixins and their methods
mixins = {
    "schema.py": {
        "class": "SchemaMigrationMixin",
        "methods": [
            "drop_recreate_dest_db",
            "step4a_migrate_schema_pre_data",
            "step4b_migrate_schema_post_data"
        ]
    },
    "replication.py": {
        "class": "CoreReplicationMixin",
        "methods": [
            "step5_setup_source",
            "_resolve_source_host",
            "step6_setup_destination",
            "step10_terminate_replication",
            "setup_reverse_replication",
            "cleanup_reverse_replication"
        ]
    },
    "monitoring.py": {
        "class": "MonitoringMixin",
        "methods": [
            "wait_for_sync",
            "get_initial_copy_progress",
            "get_replication_status"
        ]
    },
    "data_sync.py": {
        "class": "DataSyncMixin",
        "methods": [
            "sync_large_objects",
            "sync_unlogged_tables"
        ]
    }
}

os.makedirs("src/migrator_components", exist_ok=True)
with open("src/migrator_components/__init__.py", "w") as f:
    pass

for filename, mixin_data in mixins.items():
    file_content = [
        "import logging",
        "import time",
        "import re",
        "from src.db import PostgresClient, execute_shell_command, resolve_target_schemas, pgpass_context, pretty_size",
        "",
        f"class {mixin_data['class']}:"
    ]
    
    for method in mixin_data["methods"]:
        # Find the method in content
        # It starts with "    def method_name("
        # It ends before the next "    def " or end of file
        pattern = r"(    def " + method + r"\(.*?)(?=^    def |\Z)"
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)
        if match:
            file_content.append(match.group(1).rstrip())
            
    with open(f"src/migrator_components/{filename}", "w") as f:
        f.write("\n".join(file_content) + "\n")

print("Files generated in src/migrator_components/")

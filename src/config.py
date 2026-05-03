import configparser
import os


class Config:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        self.config.read(config_path)

    def get_source_dict(self):
        return dict(self.config['source'])

    def get_dest_dict(self):
        return dict(self.config['destination'])

    def _get_conn_string(self, section):
        s = self.config[section]
        # For psycopg, a dict is better, but this handles URI too
        return f"postgresql://{s['user']}:{s['password']}@{s['host']}:{s['port']}/{s['database']}"

    def get_source_conn(self):
        return self._get_conn_string('source')

    def get_dest_conn(self):
        return self._get_conn_string('destination')

    def get_replication(self):
        import re
        rep = dict(self.config['replication'])

        source_db = self.config['source']['database'].lower()
        target_schema = rep.get('target_schema', 'public').lower()

        safe_db = re.sub(r'[^a-z0-9_]', '_', source_db)
        safe_schema = re.sub(r'[^a-z0-9_]', '_', target_schema)
        suffix = f"_{safe_db}_{safe_schema}"

        for key, default in [('publication_name', 'migrator_pub'), (
                'subscription_name', 'migrator_sub'), ('slot_name', 'migrator_slot')]:
            val = rep.get(key, default)
            if suffix not in val:
                rep[key] = f"{val}{suffix}"
            else:
                rep[key] = val

        return rep

    def get_target_schemas(self):
        """Return a list of target schemas or ['all']."""
        target = self.config['replication'].get(
            'target_schema', 'public').strip().lower()
        if target == 'all':
            return ['all']
        # Handle comma-separated list
        return [s.strip() for s in target.split(',') if s.strip()]

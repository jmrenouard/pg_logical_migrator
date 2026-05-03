import configparser
import os


class Config:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.override_db = os.environ.get('PG_MIGRATOR_OVERRIDE_DB')
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        self.config.read(config_path)

    def set_override_db(self, db_name):
        """Override the database name for multi-database migration."""
        self.override_db = db_name

    def get_source_dict(self):
        return dict(self.config['source'])

    def get_dest_dict(self):
        return dict(self.config['destination'])

    def _get_conn_string(self, section, db_name=None):
        s = self.config[section]
        db = db_name if db_name else (self.override_db if self.override_db else s['database'])
        # For psycopg, a dict is better, but this handles URI too
        return f"postgresql://{s['user']}:{s['password']}@{s['host']}:{s['port']}/{db}"

    def get_source_conn(self, db_name=None):
        return self._get_conn_string('source', db_name)

    def get_dest_conn(self, db_name=None):
        return self._get_conn_string('destination', db_name)

    def get_databases(self):
        """Return a list of databases to migrate, or ['*'] for all."""
        # First check replication section
        if 'replication' in self.config and 'databases' in self.config['replication']:
            dbs = self.config['replication']['databases'].strip()
            if dbs == '*':
                return ['*']
            return [d.strip() for d in dbs.split(',') if d.strip()]
        
        # Fallback to general section
        if 'general' in self.config and 'databases' in self.config['general']:
            dbs = self.config['general']['databases'].strip()
            if dbs == '*':
                return ['*']
            return [d.strip() for d in dbs.split(',') if d.strip()]
            
        # Fallback to single db in source or override
        if self.override_db:
            return [self.override_db]
            
        if 'source' in self.config and 'database' in self.config['source']:
            return [self.config['source']['database']]
            
        return []

    def get_replication(self, db_name=None):
        import re
        rep = dict(self.config['replication'])

        source_db = db_name if db_name else (self.override_db if self.override_db else self.config['source']['database'].lower())
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

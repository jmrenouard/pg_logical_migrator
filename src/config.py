import configparser
import os


class Config:
    def __init__(self, config_path, override_db=None):
        self.config_path = config_path
        self.config = configparser.ConfigParser()
        self.override_db = override_db
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        self.config.read(config_path)

    def set_override_db(self, db_name):
        """Override the database name for multi-database migration."""
        self.override_db = db_name

    def get_source_dict(self, db_name=None):
        if not db_name:
            db_name = self.override_db
        if 'source' not in self.config:
            base = {}
        else:
            base = dict(self.config['source'])
            
        if db_name and f"database:{db_name}" in self.config:
            db_sec = self.config[f"database:{db_name}"]
            for k, v in db_sec.items():
                if k.startswith('source_'):
                    base[k[7:]] = v
        
        if db_name:
            base['database'] = db_name
            
        return base

    def get_dest_dict(self, db_name=None):
        if not db_name:
            db_name = self.override_db
        if 'destination' not in self.config:
            base = {}
        else:
            base = dict(self.config['destination'])
            
        if db_name and f"database:{db_name}" in self.config:
            db_sec = self.config[f"database:{db_name}"]
            for k, v in db_sec.items():
                if k.startswith('dest_'):
                    base[k[5:]] = v

        if db_name:
            base['database'] = db_name

        return base

    def _get_conn_string(self, section, db_name=None):
        if not db_name:
            db_name = self.override_db
            
        if section == 'source':
            s = self.get_source_dict(db_name)
        elif section == 'destination':
            s = self.get_dest_dict(db_name)
        else:
            if section not in self.config:
                return f"postgresql://user:pass@localhost:5432/postgres"
            s = dict(self.config[section])
            
        db = db_name if db_name else s.get('database', 'postgres')
        user = s.get('user', 'postgres')
        password = s.get('password', '')
        host = s.get('host', 'localhost')
        port = s.get('port', '5432')
        return f"postgresql://{user}:{password}@{host}:{port}/{db}"

    def get_source_conn(self, db_name=None):
        return self._get_conn_string('source', db_name)

    def get_dest_conn(self, db_name=None):
        return self._get_conn_string('destination', db_name)

    def get_databases(self):
        """Return a list of databases to migrate."""
        dbs_str = None
        if 'replication' in self.config and 'databases' in self.config['replication']:
            dbs_str = self.config['replication']['databases'].strip()
        elif 'general' in self.config and 'databases' in self.config['general']:
            dbs_str = self.config['general']['databases'].strip()

        if dbs_str and dbs_str.lower() in ('*', 'all'):
            try:
                from src.db import PostgresClient
                # Temporarily override dbname to postgres to run the query
                conn_uri = self.get_source_conn(db_name='postgres')
                client = PostgresClient(conn_uri)
                query = "SELECT datname FROM pg_database WHERE datistemplate = false AND datallowconn = true AND datname NOT IN ('postgres', 'rdsadmin');"
                res = client.execute_query(query)
                if res:
                    return [r['datname'] for r in res]
                return []
            except Exception as e:
                import logging
                logging.error(f"Could not discover databases dynamically: {e}")
                return []
        
        if dbs_str:
            return [d.strip() for d in dbs_str.split(',') if d.strip()]
            
        if self.override_db:
            return [self.override_db]
            
        if 'source' in self.config and 'database' in self.config['source']:
            return [self.config['source']['database']]
            
        return []

    def get_replication(self, db_name=None):
        import re
        import hashlib
        
        if 'replication' not in self.config:
            rep = {}
        else:
            rep = dict(self.config['replication'])

        source_db = db_name
        if not source_db:
            source_db = self.override_db
        if not source_db and 'source' in self.config:
            source_db = self.config['source'].get('database')
        if not source_db:
            source_db = 'postgres'
        source_db = source_db.lower()
        
        schemas = self.get_target_schemas(source_db)

        safe_db = re.sub(r'[^a-z0-9_]', '_', source_db)
        
        if schemas == ['all']:
            safe_schema = 'all'
        elif len(schemas) == 1:
            safe_schema = re.sub(r'[^a-z0-9_]', '_', schemas[0])
        else:
            schemas_str = ",".join(sorted(schemas))
            hash_str = hashlib.md5(schemas_str.encode()).hexdigest()[:8]
            safe_schema = f"multi_{hash_str}"

        suffix = f"_{safe_db}_{safe_schema}"

        for key, default in [('publication_name', 'migrator_pub'), (
                'subscription_name', 'migrator_sub'), ('slot_name', 'migrator_slot')]:
            val = rep.get(key, default)
            if suffix not in val:
                rep[key] = f"{val}{suffix}"
            else:
                rep[key] = val

        return rep

    def get_target_schemas(self, db_name=None):
        """Return a list of target schemas or ['all']."""
        if not db_name:
            db_name = self.override_db
            
        target = None
        if db_name and f"database:{db_name}" in self.config:
            target = self.config[f"database:{db_name}"].get('target_schema')
            
        if not target:
            if 'replication' in self.config:
                target = self.config['replication'].get('target_schema', 'public')
            else:
                target = 'public'
                
        target = target.strip().lower()
        if target == 'all' or target == '*':
            return ['all']
        # Handle comma-separated list
        return [s.strip() for s in target.split(',') if s.strip()]

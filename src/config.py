import configparser
import os

class Config:
    def __init__(self, config_path):
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
        return self.config['replication']

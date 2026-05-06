"""
schema_utils.py — Centralised schema filtering logic.

This module provides the SchemaFilterMixin used by any class that needs
to build SQL WHERE clauses restricting queries to the user-configured
target schemas.  It eliminates the triplication previously present in
DBChecker, PostSync, and Validator.

Usage:
    class MyChecker(SchemaFilterMixin):
        def __init__(self, source, dest=None, config=None):
            super().__init__(config=config)
            self.source = source
            ...
"""

from src.db import resolve_target_schemas


class SchemaFilterMixin:
    """Mixin providing a reusable ``_get_schema_filter()`` method.

    Any class that inherits from this mixin gains the ability to generate
    a SQL ``AND …`` clause that limits queries to the schemas declared in
    the project configuration file (``[replication] target_schema``).

    The mixin expects:
      - ``self.config`` exposing ``get_target_schemas()``
      - ``self.source`` (a PostgresClient) used by ``resolve_target_schemas``
    """

    def _get_schema_filter(self, nspname_col: str = "n.nspname") -> str:
        """Build a SQL AND clause filtering on the configured target schemas.

        When ``target_schema = all`` in the config, this method resolves the
        actual schema names from the database (excluding system/extension
        schemas) via ``resolve_target_schemas()``.

        Args:
            nspname_col: The column/expression representing the schema name
                         in the calling query (default ``n.nspname``).

        Returns:
            A string like ``AND n.nspname IN ('public', 's2')`` when specific
            schemas are configured, or an empty string when ``target_schema``
            is ``all`` or when no config is available.
        """
        if not self.config:
            return ""
        source = getattr(self, 'source', None)
        override_db = getattr(self.config, 'override_db', None)
        if source:
            schemas = resolve_target_schemas(source, self.config, override_db)
        else:
            schemas = self.config.get_target_schemas(override_db)
        if schemas == ['all']:
            return ""
        schema_list = ", ".join([f"'{s}'" for s in schemas])
        return f"AND {nspname_col} IN ({schema_list})"

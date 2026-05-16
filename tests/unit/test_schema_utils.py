"""
test_schema_utils.py — Unit tests for the centralised SchemaFilterMixin.

Tests the _get_schema_filter() method extracted from checker.py, post_sync.py,
and validation.py to verify consistent schema-level SQL filtering.
"""

from unittest.mock import MagicMock, patch
from src.schema_utils import SchemaFilterMixin


class FakeConsumer(SchemaFilterMixin):
    """Test class that inherits SchemaFilterMixin to verify its behaviour."""

    def __init__(self, source=None, config=None):
        super().__init__()
        self.source = source
        self.config = config


class TestSchemaFilterNoConfig:
    """Verify _get_schema_filter returns empty string when no config is set."""

    def test_no_config_returns_empty(self):
        """When config is None, no filter should be applied."""
        consumer = FakeConsumer()
        assert consumer._get_schema_filter() == ""

    def test_no_config_custom_column_returns_empty(self):
        """Custom nspname_col should not matter when config is absent."""
        consumer = FakeConsumer()
        assert consumer._get_schema_filter(nspname_col="s.schema_name") == ""


class TestSchemaFilterAllSchemas:
    """Verify _get_schema_filter returns empty string for 'all' schema target."""

    def test_all_schemas_no_source(self):
        """When schemas=['all'] and no DB client, return empty filter."""
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ['all']
        mock_config.override_db = None
        consumer = FakeConsumer(config=mock_config)
        assert consumer._get_schema_filter() == ""

    def test_all_schemas_with_resolve(self):
        """When resolve_target_schemas returns ['all'], return empty filter."""
        mock_config = MagicMock()
        mock_config.override_db = None
        mock_source = MagicMock()
        consumer = FakeConsumer(source=mock_source, config=mock_config)
        with patch("src.schema_utils.resolve_target_schemas", return_value=['all']):
            assert consumer._get_schema_filter() == ""


class TestSchemaFilterSpecificSchemas:
    """Verify _get_schema_filter builds correct SQL for specific schemas."""

    def test_single_schema(self):
        """A single target schema should produce AND n.nspname IN ('public')."""
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ['public']
        mock_config.override_db = None
        consumer = FakeConsumer(config=mock_config)
        result = consumer._get_schema_filter()
        assert result == "AND n.nspname IN ('public')"

    def test_multiple_schemas(self):
        """Multiple schemas should all appear in the IN clause."""
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ['public', 'sales', 'hr']
        mock_config.override_db = None
        consumer = FakeConsumer(config=mock_config)
        result = consumer._get_schema_filter()
        assert "'public'" in result
        assert "'sales'" in result
        assert "'hr'" in result
        assert result.startswith("AND n.nspname IN (")

    def test_custom_nspname_col(self):
        """The nspname_col parameter should replace the default column name."""
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ['public']
        mock_config.override_db = None
        consumer = FakeConsumer(config=mock_config)
        result = consumer._get_schema_filter(nspname_col="s.schema_name")
        assert result == "AND s.schema_name IN ('public')"

    def test_with_source_client_and_resolve(self):
        """When a source client exists, resolve_target_schemas should be called."""
        mock_config = MagicMock()
        mock_config.override_db = 'mydb'
        mock_source = MagicMock()
        consumer = FakeConsumer(source=mock_source, config=mock_config)
        with patch("src.schema_utils.resolve_target_schemas",
                   return_value=['public', 'analytics']) as mock_resolve:
            result = consumer._get_schema_filter()
            mock_resolve.assert_called_once_with(mock_source, mock_config, 'mydb')
            assert "'public'" in result
            assert "'analytics'" in result


class TestResolveTargetSchemas:
    """Tests for the resolve_target_schemas helper in src.db."""

    def test_non_all_returns_config_value(self):
        """When config returns specific schemas, they are returned directly."""
        from src.db import resolve_target_schemas
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ['public', 'sales']
        mock_client = MagicMock()
        result = resolve_target_schemas(mock_client, mock_config)
        assert result == ['public', 'sales']

    def test_all_queries_database(self):
        """When config returns ['all'], the DB should be queried for schema names."""
        from src.db import resolve_target_schemas
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ['all']
        mock_client = MagicMock()
        mock_client.execute_query.return_value = [
            {'schema_name': 'public'},
            {'schema_name': 'app'},
        ]
        result = resolve_target_schemas(mock_client, mock_config)
        assert result == ['public', 'app']

    def test_all_with_empty_result_returns_all(self):
        """When the DB returns no schemas, fall back to ['all']."""
        from src.db import resolve_target_schemas
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ['all']
        mock_client = MagicMock()
        mock_client.execute_query.return_value = []
        result = resolve_target_schemas(mock_client, mock_config)
        assert result == ['all']

    def test_all_with_query_failure_returns_all(self):
        """When the DB query fails, fall back to ['all']."""
        from src.db import resolve_target_schemas
        mock_config = MagicMock()
        mock_config.get_target_schemas.return_value = ['all']
        mock_client = MagicMock()
        mock_client.execute_query.side_effect = Exception("Connection refused")
        result = resolve_target_schemas(mock_client, mock_config)
        assert result == ['all']

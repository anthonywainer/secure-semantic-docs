"""Tests for metadata_builder conform_document_metadata and _cast_field."""

from unittest.mock import MagicMock, patch


def _make_raw_df() -> MagicMock:
    df = MagicMock()
    df.select.return_value = df
    return df


def _mock_schema(field_names: list[str]) -> list[MagicMock]:
    fields = []
    for name in field_names:
        f = MagicMock()
        f.name = name
        f.dataType = MagicMock()
        fields.append(f)
    return fields


class TestConformDocumentMetadata:
    def test_returns_dataframe(self):
        """conform_document_metadata returns a DataFrame from the final select call."""
        from secure_semantic_docs.processing.metadata_builder import conform_document_metadata

        raw_df = _make_raw_df()
        schema = _mock_schema(["document_id", "ingestion_timestamp"])

        with (
            patch("secure_semantic_docs.processing.metadata_builder.col", return_value=MagicMock()),
            patch("secure_semantic_docs.processing.metadata_builder.lit", return_value=MagicMock()),
            patch("secure_semantic_docs.processing.metadata_builder.load_schema", return_value=schema)
        ):
            result = conform_document_metadata(raw_df)

        assert result is not None

    def test_select_called_twice(self):
        """conform_document_metadata calls .select() twice — column selection then cast."""
        from secure_semantic_docs.processing.metadata_builder import conform_document_metadata

        raw_df = _make_raw_df()
        schema = _mock_schema(["document_id"])

        with (
            patch("secure_semantic_docs.processing.metadata_builder.col", return_value=MagicMock()),
            patch("secure_semantic_docs.processing.metadata_builder.lit", return_value=MagicMock()),
            patch("secure_semantic_docs.processing.metadata_builder.load_schema", return_value=schema)
        ):
            conform_document_metadata(raw_df)

        assert raw_df.select.call_count == 2


class TestCastField:
    def test_ingestion_timestamp_uses_lit(self):
        """_cast_field uses lit() for the ingestion_timestamp field."""
        # noinspection PyProtectedMember
        from secure_semantic_docs.processing.metadata_builder import _cast_field  # noqa: SLF001

        mock_lit_result = MagicMock()
        field = MagicMock()
        field.name = "ingestion_timestamp"

        with patch("secure_semantic_docs.processing.metadata_builder.lit", return_value=mock_lit_result) as mock_lit:
            _cast_field(field, "2026-01-01T00:00:00Z")

        mock_lit.assert_called_once_with("2026-01-01T00:00:00Z")

    def test_regular_field_uses_col(self):
        """_cast_field uses col() for non-ingestion_timestamp fields."""
        # noinspection PyProtectedMember
        from secure_semantic_docs.processing.metadata_builder import _cast_field  # noqa: SLF001

        mock_col_result = MagicMock()
        field = MagicMock()
        field.name = "document_id"

        with patch("secure_semantic_docs.processing.metadata_builder.col", return_value=mock_col_result) as mock_col:
            _cast_field(field, "2026-01-01T00:00:00Z")

        mock_col.assert_called_once_with("document_id")

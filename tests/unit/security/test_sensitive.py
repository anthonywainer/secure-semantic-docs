"""Unit tests for sensitive information detection."""


from secure_semantic_docs.models import SensitivityResult
from secure_semantic_docs.security.sensitive_detector import (
    analyse_chunk,
    enrich_chunks_with_sensitivity
)


class TestAnalyseChunk:
    def test_clean_public_text_scores_zero(self):
        result = analyse_chunk("This is a plain document with no sensitive data.", "public")
        assert result.sensitivity_score == 0.0
        assert result.detected_sensitive_types == []
        assert result.requires_encryption is False
        assert result.requires_restricted_access is False

    def test_detects_email_pattern(self):
        result = analyse_chunk("Contact alice@example.com for details.", "public")
        assert "email" in result.detected_sensitive_types

    def test_detects_employee_id_pattern(self):
        result = analyse_chunk("Employee EMP-123456 submitted the request.", "public")
        assert "employee_id" in result.detected_sensitive_types

    def test_detects_client_id_pattern(self):
        result = analyse_chunk("Assigned to client CLT-AB-12345.", "public")
        assert "client_id" in result.detected_sensitive_types

    def test_detects_project_code_pattern(self):
        result = analyse_chunk("Project PROJ-ABC-001 is on track.", "public")
        assert "project_code" in result.detected_sensitive_types

    def test_detects_financial_amount_pattern(self):
        result = analyse_chunk("Total cost is $12,345.67.", "public")
        assert "financial_amount" in result.detected_sensitive_types

    def test_detects_token_pattern(self):
        result = analyse_chunk("Use token tok_abcdef1234567890 to authenticate.", "public")
        assert "token" in result.detected_sensitive_types

    def test_detects_security_keyword(self):
        result = analyse_chunk("A security vulnerability was found.", "public")
        assert any("vulnerability" in t for t in result.detected_sensitive_types)

    def test_detects_multi_word_security_keyword(self):
        result = analyse_chunk("This is a penetration test report.", "public")
        assert any("penetration_test" in t for t in result.detected_sensitive_types)

    def test_keyword_not_duplicated(self):
        result = analyse_chunk("token tok_abcdef1234567890 is a token", "public")
        token_keyword_hits = [t for t in result.detected_sensitive_types if t == "keyword:token"]
        assert len(token_keyword_hits) <= 1

    def test_classification_base_score_applied(self):
        public_result = analyse_chunk("clean text", "public")
        restricted_result = analyse_chunk("clean text", "restricted")
        assert restricted_result.sensitivity_score > public_result.sensitivity_score

    def test_unknown_classification_uses_zero_base(self):
        result = analyse_chunk("clean text", "unknown_level")
        assert result.sensitivity_score == 0.0

    def test_score_capped_at_one(self):
        many_patterns = (
            "alice@example.com EMP-123456 CLT-AB-12345 PROJ-ABC-001 "
            "$12,345.67 tok_abcdef1234567890 vulnerability incident breach"
        )
        result = analyse_chunk(many_patterns, "restricted")
        assert result.sensitivity_score <= 1.0

    def test_requires_encryption_at_threshold(self):
        result = analyse_chunk(
            "alice@example.com EMP-123456 $99,999.99 vulnerability payroll",
            "restricted"
        )
        assert result.requires_encryption is True

    def test_requires_restricted_access_at_threshold(self):
        result = analyse_chunk(
            "alice@example.com EMP-123456 $99,999.99 vulnerability payroll breach",
            "restricted"
        )
        assert result.requires_restricted_access is True

    def test_returns_sensitivity_result_dataclass(self):
        result = analyse_chunk("hello", "public")
        assert isinstance(result, SensitivityResult)


class TestEnrichChunksWithSensitivity:
    @staticmethod
    def _make_chunk(text: str = "hello world", classification: str = "public") -> dict:
        return {"chunk_text": text, "classification": classification, "chunk_id": "c1"}

    def test_adds_sensitivity_fields(self):
        chunks = [self._make_chunk()]
        enriched = enrich_chunks_with_sensitivity(chunks)
        assert "sensitivity_score" in enriched[0]
        assert "detected_sensitive_types" in enriched[0]
        assert "requires_encryption" in enriched[0]
        assert "requires_restricted_access" in enriched[0]

    def test_preserves_original_fields(self):
        chunks = [self._make_chunk()]
        enriched = enrich_chunks_with_sensitivity(chunks)
        assert enriched[0]["chunk_id"] == "c1"
        assert enriched[0]["chunk_text"] == "hello world"

    def test_empty_list_returns_empty(self):
        assert enrich_chunks_with_sensitivity([]) == []

    def test_multiple_chunks_all_enriched(self):
        chunks = [self._make_chunk("doc one"), self._make_chunk("doc two")]
        enriched = enrich_chunks_with_sensitivity(chunks)
        assert len(enriched) == 2
        assert all("sensitivity_score" in c for c in enriched)

    def test_missing_chunk_text_handled(self):
        chunks = [{"classification": "public", "chunk_id": "c2"}]
        enriched = enrich_chunks_with_sensitivity(chunks)
        assert enriched[0]["sensitivity_score"] == 0.0

    def test_missing_classification_defaults_to_public(self):
        chunks = [{"chunk_text": "hello", "chunk_id": "c3"}]
        enriched = enrich_chunks_with_sensitivity(chunks)
        assert enriched[0]["sensitivity_score"] == 0.0

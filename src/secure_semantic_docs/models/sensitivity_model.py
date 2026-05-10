"""Data model for sensitivity analysis results."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SensitivityResult:
    """Result of a sensitivity analysis for a single chunk."""

    sensitivity_score: float
    detected_sensitive_types: list[str]
    requires_encryption: bool
    requires_restricted_access: bool

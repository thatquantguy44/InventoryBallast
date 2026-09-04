"""Structured validation errors.

Section 9.8 of ``01_SPEC.md`` requires that validation return structured issue codes and
locations, and that public API calls raise one ``InputValidationError`` containing every
detectable issue rather than failing on the first field.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """One structured, located validation finding.

    Attributes:
        code: Stable machine-readable issue code (e.g. ``"BALANCE_RECONCILIATION_FAILED"``).
        message: Human-readable description of the failure.
        location: Dotted/bracketed path to the offending field or record
            (e.g. ``"inventory[2].available_to_lend_shares"``).
    """

    code: str
    message: str
    location: str


class InputValidationError(Exception):
    """Raised with every detectable validation issue attached, never just the first one."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        if not issues:
            raise ValueError("InputValidationError requires at least one ValidationIssue")
        self.issues = issues
        summary = "; ".join(f"[{i.code}] {i.location}: {i.message}" for i in issues)
        super().__init__(f"{len(issues)} validation issue(s): {summary}")


class ConfigurationError(Exception):
    """Raised for configuration merge, precedence, or schema failures."""


class RegistrationError(Exception):
    """Raised for duplicate or malformed component/problem-family registration."""

"""Shared exception types for PromptProof."""


class PromptProofError(Exception):
    """Base error for configuration / suite problems (exit code 2)."""


class TemplateError(PromptProofError):
    """Raised when a prompt template cannot be rendered."""


class AssertionConfigError(PromptProofError):
    """Raised when an assertion in a suite is malformed or unknown."""

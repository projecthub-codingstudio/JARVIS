"""Typed error taxonomy for the JARVIS system.

All error codes are defined here. Modules raise JarvisError subclasses
with an ErrorCode to enable programmatic error handling.
"""

from __future__ import annotations

from enum import Enum, unique


@unique
class ErrorCode(str, Enum):
    """Exhaustive error code enumeration."""

    # Retrieval errors
    QUERY_DECOMPOSE_FAILED = "QUERY_DECOMPOSE_FAILED"
    FTS_SEARCH_FAILED = "FTS_SEARCH_FAILED"
    VECTOR_SEARCH_FAILED = "VECTOR_SEARCH_FAILED"
    HYBRID_FUSION_FAILED = "HYBRID_FUSION_FAILED"
    NO_EVIDENCE_FOUND = "NO_EVIDENCE_FOUND"

    # Evidence errors
    EVIDENCE_BUILD_FAILED = "EVIDENCE_BUILD_FAILED"
    CITATION_UNRESOLVABLE = "CITATION_UNRESOLVABLE"

    # Runtime errors
    MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"
    GENERATION_FAILED = "GENERATION_FAILED"
    EMBEDDING_FAILED = "EMBEDDING_FAILED"

    # Indexing errors
    PARSE_FAILED = "PARSE_FAILED"
    CHUNK_FAILED = "CHUNK_FAILED"
    INDEX_WRITE_FAILED = "INDEX_WRITE_FAILED"

    # Tool errors
    TOOL_NOT_REGISTERED = "TOOL_NOT_REGISTERED"
    TOOL_EXECUTION_FAILED = "TOOL_EXECUTION_FAILED"
    APPROVAL_DENIED = "APPROVAL_DENIED"

    # Access errors
    PATH_OUTSIDE_SCOPE = "PATH_OUTSIDE_SCOPE"
    ACCESS_DENIED = "ACCESS_DENIED"

    # Governor errors
    RESOURCE_LIMIT_EXCEEDED = "RESOURCE_LIMIT_EXCEEDED"
    GOVERNOR_SHUTDOWN = "GOVERNOR_SHUTDOWN"

    # Storage errors
    SQLITE_ERROR = "SQLITE_ERROR"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"

    # General
    INTERNAL_ERROR = "INTERNAL_ERROR"
    CONFIGURATION_ERROR = "CONFIGURATION_ERROR"


class JarvisError(Exception):
    """Base exception for all JARVIS errors."""

    def __init__(self, code: ErrorCode, message: str, details: dict[str, object] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


class RetrievalError(JarvisError):
    """Errors during the retrieval pipeline."""


class EvidenceError(JarvisError):
    """Errors during evidence building."""


class RuntimeError_(JarvisError):
    """Errors during LLM/embedding runtime (suffixed to avoid shadowing builtins)."""


class IndexingError(JarvisError):
    """Errors during document indexing."""


class ToolError(JarvisError):
    """Errors during tool execution."""


class AccessError(JarvisError):
    """Errors related to path/permission access violations."""


class GovernorError(JarvisError):
    """Errors from the governor subsystem."""


class StorageError(JarvisError):
    """Errors from SQLite or schema operations."""

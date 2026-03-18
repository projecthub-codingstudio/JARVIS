"""Contract tests for error taxonomy."""

from __future__ import annotations

import pytest

from jarvis.contracts.errors import (
    AccessError,
    ErrorCode,
    EvidenceError,
    GovernorError,
    IndexingError,
    JarvisError,
    RetrievalError,
    RuntimeError_,
    StorageError,
    ToolError,
)


class TestErrorCode:
    def test_all_codes_are_unique(self) -> None:
        values = [e.value for e in ErrorCode]
        assert len(values) == len(set(values))

    def test_retrieval_codes_exist(self) -> None:
        assert ErrorCode.QUERY_DECOMPOSE_FAILED
        assert ErrorCode.FTS_SEARCH_FAILED
        assert ErrorCode.VECTOR_SEARCH_FAILED
        assert ErrorCode.HYBRID_FUSION_FAILED
        assert ErrorCode.NO_EVIDENCE_FOUND

    def test_string_serialization(self) -> None:
        code = ErrorCode.MODEL_LOAD_FAILED
        assert code.value == "MODEL_LOAD_FAILED"
        assert ErrorCode("MODEL_LOAD_FAILED") == code


class TestJarvisError:
    def test_base_error(self) -> None:
        err = JarvisError(ErrorCode.INTERNAL_ERROR, "Something went wrong")
        assert err.code == ErrorCode.INTERNAL_ERROR
        assert err.message == "Something went wrong"
        assert err.details == {}
        assert str(err) == "Something went wrong"

    def test_error_with_details(self) -> None:
        err = JarvisError(
            ErrorCode.SQLITE_ERROR, "DB locked",
            details={"path": "/tmp/test.db"},
        )
        assert err.details["path"] == "/tmp/test.db"


class TestErrorSubclasses:
    def test_retrieval_error(self) -> None:
        err = RetrievalError(ErrorCode.FTS_SEARCH_FAILED, "FTS failed")
        assert isinstance(err, JarvisError)
        assert isinstance(err, RetrievalError)

    def test_evidence_error(self) -> None:
        err = EvidenceError(ErrorCode.EVIDENCE_BUILD_FAILED, "build failed")
        assert isinstance(err, JarvisError)

    def test_runtime_error(self) -> None:
        err = RuntimeError_(ErrorCode.MODEL_LOAD_FAILED, "model failed")
        assert isinstance(err, JarvisError)

    def test_indexing_error(self) -> None:
        err = IndexingError(ErrorCode.PARSE_FAILED, "parse failed")
        assert isinstance(err, JarvisError)

    def test_tool_error(self) -> None:
        err = ToolError(ErrorCode.TOOL_NOT_REGISTERED, "unknown tool")
        assert isinstance(err, JarvisError)

    def test_access_error(self) -> None:
        err = AccessError(ErrorCode.PATH_OUTSIDE_SCOPE, "out of scope")
        assert isinstance(err, JarvisError)

    def test_governor_error(self) -> None:
        err = GovernorError(ErrorCode.RESOURCE_LIMIT_EXCEEDED, "memory limit")
        assert isinstance(err, JarvisError)

    def test_storage_error(self) -> None:
        err = StorageError(ErrorCode.SQLITE_ERROR, "db error")
        assert isinstance(err, JarvisError)

    def test_all_subclasses_catchable_as_jarvis_error(self) -> None:
        errors = [
            RetrievalError(ErrorCode.FTS_SEARCH_FAILED, "a"),
            EvidenceError(ErrorCode.EVIDENCE_BUILD_FAILED, "b"),
            RuntimeError_(ErrorCode.MODEL_LOAD_FAILED, "c"),
            IndexingError(ErrorCode.PARSE_FAILED, "d"),
            ToolError(ErrorCode.TOOL_NOT_REGISTERED, "e"),
            AccessError(ErrorCode.PATH_OUTSIDE_SCOPE, "f"),
            GovernorError(ErrorCode.RESOURCE_LIMIT_EXCEEDED, "g"),
            StorageError(ErrorCode.SQLITE_ERROR, "h"),
        ]
        for err in errors:
            try:
                raise err
            except JarvisError as caught:
                assert caught.code is not None

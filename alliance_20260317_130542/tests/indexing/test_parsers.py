"""Tests for DocumentParser."""
from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.contracts import DocumentRecord, IndexingStatus, AccessStatus
from jarvis.indexing.parsers import DocumentParser


class TestDetectType:
    def test_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "readme.md"
        f.write_text("# Hello")
        assert DocumentParser().detect_type(f) == "markdown"

    def test_python(self, tmp_path: Path) -> None:
        f = tmp_path / "app.py"
        f.write_text("print('hi')")
        assert DocumentParser().detect_type(f) == "python"

    def test_typescript(self, tmp_path: Path) -> None:
        f = tmp_path / "index.ts"
        f.write_text("const x = 1;")
        assert DocumentParser().detect_type(f) == "typescript"

    def test_yaml(self, tmp_path: Path) -> None:
        f = tmp_path / "config.yaml"
        f.write_text("key: value")
        assert DocumentParser().detect_type(f) == "yaml"

    def test_plain_text(self, tmp_path: Path) -> None:
        f = tmp_path / "notes.txt"
        f.write_text("some notes")
        assert DocumentParser().detect_type(f) == "text"

    def test_unknown_extension(self, tmp_path: Path) -> None:
        f = tmp_path / "data.bin"
        f.write_bytes(b"\x00\x01")
        assert DocumentParser().detect_type(f) == "text"


class TestParse:
    def test_parse_markdown(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("# Title\n\nParagraph text.")
        text = DocumentParser().parse(f)
        assert "Title" in text
        assert "Paragraph text." in text

    def test_parse_python(self, tmp_path: Path) -> None:
        f = tmp_path / "mod.py"
        content = '"""Docstring."""\n\ndef foo():\n    pass\n'
        f.write_text(content)
        text = DocumentParser().parse(f)
        assert "Docstring" in text
        assert "def foo" in text

    def test_parse_nonexistent_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            DocumentParser().parse(Path("/nonexistent/file.md"))

    def test_parse_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert DocumentParser().parse(f) == ""

    def test_parse_korean_content(self, tmp_path: Path) -> None:
        f = tmp_path / "korean.md"
        f.write_text("# 제목\n\n한국어 문서 내용입니다.")
        text = DocumentParser().parse(f)
        assert "제목" in text
        assert "한국어" in text


class TestCreateRecord:
    def test_creates_record_with_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("content here")
        record = DocumentParser().create_record(f)
        assert isinstance(record, DocumentRecord)
        assert record.path == str(f)
        assert record.size_bytes == f.stat().st_size
        assert record.content_hash  # non-empty SHA-256
        assert record.indexing_status == IndexingStatus.PENDING
        assert record.access_status == AccessStatus.ACCESSIBLE

    def test_record_hash_changes_with_content(self, tmp_path: Path) -> None:
        f = tmp_path / "doc.md"
        f.write_text("version 1")
        r1 = DocumentParser().create_record(f)
        f.write_text("version 2")
        r2 = DocumentParser().create_record(f)
        assert r1.content_hash != r2.content_hash

    def test_record_for_inaccessible_file(self) -> None:
        with pytest.raises(FileNotFoundError):
            DocumentParser().create_record(Path("/nonexistent"))

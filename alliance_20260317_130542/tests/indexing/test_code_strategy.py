"""Tests for CodeChunkStrategy — function/class boundary splitting."""
from jarvis.contracts import DocumentElement
from jarvis.indexing.strategies.code import CodeChunkStrategy


class TestCodeChunkStrategy:
    def test_splits_at_function_boundaries(self) -> None:
        code = "def foo():\n    return 1\n\ndef bar():\n    return 2\n\ndef baz():\n    return 3\n"
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy(max_tokens=20)  # Force split
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) >= 2
        texts = [c.text for c in chunks]
        assert any("def foo" in t for t in texts)

    def test_class_with_methods(self) -> None:
        code = "class MyClass:\n    def method_a(self):\n        pass\n\n    def method_b(self):\n        pass\n"
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) >= 1

    def test_short_code_single_chunk(self) -> None:
        code = "x = 1\n"
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) == 1

    def test_empty_code(self) -> None:
        el = DocumentElement(element_type="code", text="", metadata={"language": "python"})
        strategy = CodeChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert chunks == []

    def test_heading_path_includes_language(self) -> None:
        code = "x = 1\n"
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy()
        chunks = strategy.chunk(el, document_id="d1")
        assert "python" in chunks[0].heading_path

    def test_large_function_splits_by_size(self) -> None:
        code = "def big_func():\n" + "".join(f"    line_{i} = {i}\n" for i in range(200))
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy(max_tokens=50)
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) > 1

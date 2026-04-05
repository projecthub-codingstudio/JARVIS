"""Tests for CodeChunkStrategy — function/class boundary splitting."""
import pytest
from jarvis.contracts import DocumentElement
from jarvis.indexing.strategies.code import CodeChunkStrategy, _split_by_tree_sitter


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


class TestTreeSitterSplitting:
    """Tests for tree-sitter AST-based code splitting."""

    def test_splits_python_functions(self) -> None:
        code = (
            "import os\n\n"
            "def hello():\n    print('world')\n\n"
            "class Foo:\n    def bar(self):\n        return 42\n\n"
            "def baz(x, y):\n    return x + y\n"
        )
        blocks = _split_by_tree_sitter(code, "python")
        assert blocks is not None
        assert len(blocks) >= 3  # imports, hello, Foo, baz
        # Each block should contain a definition
        combined = "\n".join(blocks)
        assert "def hello" in combined
        assert "class Foo" in combined
        assert "def baz" in combined

    def test_preserves_decorated_functions(self) -> None:
        code = (
            "@staticmethod\n"
            "def decorated():\n    pass\n\n"
            "def plain():\n    pass\n"
        )
        blocks = _split_by_tree_sitter(code, "python")
        assert blocks is not None
        assert any("@staticmethod" in b for b in blocks)
        assert any("def plain" in b for b in blocks)

    def test_returns_none_for_unknown_language(self) -> None:
        assert _split_by_tree_sitter("code", "brainfuck") is None

    def test_returns_none_for_no_definitions(self) -> None:
        code = "x = 1\ny = 2\nprint(x + y)\n"
        result = _split_by_tree_sitter(code, "python")
        assert result is None  # No definition boundaries

    def test_javascript_splitting(self) -> None:
        code = (
            "function greet(name) {\n  return 'Hi ' + name;\n}\n\n"
            "class Animal {\n  constructor(name) {\n    this.name = name;\n  }\n}\n"
        )
        blocks = _split_by_tree_sitter(code, "javascript")
        if blocks is not None:  # Only if tree-sitter-javascript installed
            assert len(blocks) >= 2

    def test_integration_with_chunk_strategy(self) -> None:
        """tree-sitter should be used automatically when available."""
        code = (
            "def alpha():\n    return 1\n\n"
            "def beta():\n    return 2\n\n"
            "def gamma():\n    return 3\n"
        )
        el = DocumentElement(element_type="code", text=code, metadata={"language": "python"})
        strategy = CodeChunkStrategy(max_tokens=20)
        chunks = strategy.chunk(el, document_id="d1")
        assert len(chunks) >= 2
        texts = [c.text for c in chunks]
        assert any("def alpha" in t for t in texts)

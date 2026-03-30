"""Tests for PDF structured parsing and block merging."""
from __future__ import annotations

import pytest

from jarvis.indexing.parsers import _merge_small_blocks


class TestMergeSmallBlocks:
    def test_empty_input(self) -> None:
        assert _merge_small_blocks([], min_chars=200) == []

    def test_single_large_block(self) -> None:
        block = "A" * 300
        result = _merge_small_blocks([block], min_chars=200)
        assert result == [block]

    def test_merges_small_blocks(self) -> None:
        blocks = ["short1", "short2", "short3"]
        result = _merge_small_blocks(blocks, min_chars=200)
        # All three are tiny, should be merged into one
        assert len(result) == 1
        assert "short1" in result[0]
        assert "short2" in result[0]
        assert "short3" in result[0]

    def test_large_block_stays_separate(self) -> None:
        blocks = ["A" * 250, "tiny", "B" * 250]
        result = _merge_small_blocks(blocks, min_chars=200)
        # First block: "A"*250 (≥200, emitted)
        # Second + third: "tiny" + "B"*250 (accumulated, ≥200 after "B"*250)
        assert len(result) == 2
        assert result[0] == "A" * 250

    def test_trailing_small_attaches_to_previous(self) -> None:
        blocks = ["A" * 300, "tiny"]
        result = _merge_small_blocks(blocks, min_chars=200)
        # "tiny" is < min_chars//2, so attaches to previous
        assert len(result) == 1
        assert "tiny" in result[0]
        assert result[0].startswith("A" * 300)

    def test_trailing_medium_stays_separate(self) -> None:
        blocks = ["A" * 300, "B" * 150]
        result = _merge_small_blocks(blocks, min_chars=200)
        # "B"*150 is ≥ min_chars//2 (100), so stays separate
        assert len(result) == 2

    def test_many_tiny_blocks_merged_in_groups(self) -> None:
        # 10 blocks of 50 chars each = 500 chars total
        blocks = [f"block{i:02d}" + "x" * 43 for i in range(10)]
        result = _merge_small_blocks(blocks, min_chars=200)
        # Each block is 50 chars, so 4 blocks = 200 chars → emit
        # Should produce ~2-3 merged blocks
        assert len(result) < len(blocks)
        # All content preserved
        full = "\n\n".join(result)
        for b in blocks:
            assert b in full

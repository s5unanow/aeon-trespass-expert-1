"""Block-level diff comparator for actual vs expected IR."""

from __future__ import annotations

from dataclasses import dataclass, field

from atr_schemas.page_ir_v1 import Block, PageIRV1


@dataclass(frozen=True)
class BlockDiff:
    """Difference record for a single block comparison."""

    block_id: str
    status: str  # "match", "missing", "extra", "type_mismatch"
    expected_type: str = ""
    actual_type: str = ""
    detail: str = ""


@dataclass
class CompareResult:
    """Result of comparing actual blocks against expected."""

    diffs: list[BlockDiff] = field(default_factory=list)

    @property
    def match_count(self) -> int:
        return sum(1 for d in self.diffs if d.status == "match")

    @property
    def missing_count(self) -> int:
        return sum(1 for d in self.diffs if d.status == "missing")

    @property
    def extra_count(self) -> int:
        return sum(1 for d in self.diffs if d.status == "extra")

    @property
    def mismatch_count(self) -> int:
        return sum(1 for d in self.diffs if d.status == "type_mismatch")

    @property
    def all_match(self) -> bool:
        return all(d.status == "match" for d in self.diffs)


def _block_id(block: Block) -> str:
    return block.block_id


def _block_type(block: Block) -> str:
    return block.type


def compare_blocks(actual: PageIRV1, expected_types: dict[str, str]) -> CompareResult:
    """Compare actual page blocks against expected block_id -> type mapping.

    Args:
        actual: The actual page IR.
        expected_types: Mapping of block_id to expected block type.

    Returns:
        CompareResult with per-block diff records.
    """
    diffs: list[BlockDiff] = []
    actual_map: dict[str, Block] = {_block_id(b): b for b in actual.blocks}

    for block_id, exp_type in expected_types.items():
        if block_id not in actual_map:
            diffs.append(BlockDiff(block_id=block_id, status="missing", expected_type=exp_type))
        else:
            act_type = _block_type(actual_map[block_id])
            if act_type == exp_type:
                diffs.append(
                    BlockDiff(
                        block_id=block_id,
                        status="match",
                        expected_type=exp_type,
                        actual_type=act_type,
                    )
                )
            else:
                diffs.append(
                    BlockDiff(
                        block_id=block_id,
                        status="type_mismatch",
                        expected_type=exp_type,
                        actual_type=act_type,
                        detail=f"expected {exp_type}, got {act_type}",
                    )
                )

    for block_id in actual_map:
        if block_id not in expected_types:
            diffs.append(
                BlockDiff(
                    block_id=block_id,
                    status="extra",
                    actual_type=_block_type(actual_map[block_id]),
                )
            )

    return CompareResult(diffs=diffs)


def compare_reading_order(actual: list[str], expected: list[str]) -> list[BlockDiff]:
    """Compare actual vs expected reading order, returning diffs for mismatches."""
    diffs: list[BlockDiff] = []
    max_len = max(len(actual), len(expected))

    for i in range(max_len):
        act = actual[i] if i < len(actual) else ""
        exp = expected[i] if i < len(expected) else ""
        if act == exp:
            diffs.append(BlockDiff(block_id=exp, status="match"))
        elif not act:
            diffs.append(
                BlockDiff(block_id=exp, status="missing", detail=f"position {i}: missing in actual")
            )
        elif not exp:
            diffs.append(
                BlockDiff(block_id=act, status="extra", detail=f"position {i}: extra in actual")
            )
        else:
            diffs.append(
                BlockDiff(
                    block_id=exp,
                    status="type_mismatch",
                    detail=f"position {i}: expected {exp}, got {act}",
                )
            )

    return diffs

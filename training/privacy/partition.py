"""Bounded, reversible partitioning for long local redaction prompts.

The partitioner operates on :class:`normalized_view.View`; consequently every
character handed to a caller still has an exact source range.  Context overlap
is metadata only and never expands coverage.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from normalized_view import View


class PartitionError(ValueError):
    """Input cannot be partitioned without violating a safety bound."""


@dataclass(frozen=True)
class Partition:
    view: View
    core_start: int
    core_end: int
    source_start: int
    source_end: int
    context_only: bool = False
    document_length: int = 0

    @property
    def text(self) -> str:
        return self.view.text


def _count(tokenizer: object, prompt: str) -> int:
    encode = getattr(tokenizer, "encode", None)
    if not callable(encode):
        raise PartitionError("TOKENIZER_NOT_COUNTABLE")
    result = encode(prompt)
    try:
        return len(result)
    except TypeError as exc:
        raise PartitionError("TOKENIZER_NOT_COUNTABLE") from exc


def _prompt(tokenizer: object, system: str, text: str) -> str:
    apply = getattr(tokenizer, "apply_chat_template", None)
    if not callable(apply):
        raise PartitionError("TOKENIZER_NOT_COUNTABLE")
    return apply([{"role": "system", "content": system},
                  {"role": "user", "content": text}],
                 tokenize=False, add_generation_prompt=True,
                 enable_thinking=False)


def _source_range(view: View, start: int, end: int) -> tuple[int, int]:
    if start >= end or not view.positions:
        return (0, 0)
    return view.positions[start][0], view.positions[end - 1][1]


def partition_view(view: View, tokenizer: object, system: str, *,
                   max_input: int = 2048, max_output: int = 512,
                   max_total: int | None = None, max_chunks: int = 64,
                   overlap: int = 96) -> list[Partition]:
    """Split view into bounded windows, reserving output budget per window."""
    if not isinstance(view, View) or not view.text:
        raise PartitionError("EMPTY_TEXT")
    if any(isinstance(x, bool) or not isinstance(x, int) or x <= 0 for x in
           (max_input, max_output, max_chunks)):
        raise PartitionError("INVALID_PARTITION_BUDGET")
    if max_total is None:
        max_total = max_input * max_chunks
    if not isinstance(max_total, int) or max_total <= 0:
        raise PartitionError("INVALID_PARTITION_BUDGET")
    if max_total < max_output:
        raise PartitionError("INVALID_PARTITION_BUDGET")
    overlap = max(0, int(overlap))
    length, cursor, spent = len(view.text), 0, 0
    result: list[Partition] = []
    while cursor < length:
        remaining = max_total - spent
        if remaining < max_output:
            raise PartitionError("TOTAL_BUDGET_EXCEEDED")
        # Find largest core whose *actual overlapped window* fits input budget.
        left = max(cursor - overlap, 0)
        low, high = cursor + 1, length
        best = cursor
        while low <= high:
            mid = (low + high) // 2
            right = min(length, mid + overlap)
            cost = _count(tokenizer, _prompt(tokenizer, system,
                                              view.text[left:right]))
            if cost <= max_input and cost + max_output <= remaining:
                best, low = mid, mid + 1
            else:
                high = mid - 1
        if best == cursor:
            raise PartitionError("PARTITION_INPUT_TOO_LARGE")
        # Prefer a punctuation/whitespace boundary while retaining progress.
        end = best
        for i in range(best, cursor, -1):
            if view.text[i - 1].isspace() or view.text[i - 1] in "。；;，,、.!?！？\n":
                end = i
                break
        if end <= cursor:
            end = best
        prompt_cost = _count(tokenizer, _prompt(tokenizer, system,
                                                 view.text[left:right]))
        if prompt_cost + max_output > remaining or prompt_cost > max_input:
            end = best
            prompt_cost = _count(tokenizer, _prompt(tokenizer, system,
                                                     view.text[left:right]))
        spent += prompt_cost + max_output
        right = min(length, end + overlap)
        source_start, source_end = _source_range(view, cursor, end)
        result.append(Partition(View(view.text[left:right], view.positions[left:right]),
                                cursor - left, end - left, source_start, source_end,
                                False, length))
        if len(result) >= max_chunks and end < length:
            raise PartitionError("MAX_CHUNKS_EXCEEDED")
        cursor = end
    return result


def occurrence_in_core(part: Partition, start: int, end: int) -> bool:
    """Whether a view-local occurrence belongs to core coverage."""
    return start < part.core_end and end > part.core_start

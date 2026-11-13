"""Rough token accounting for the context window."""

from __future__ import annotations


def est_tokens(text: str) -> int:
    return len(text) // 4 + 1


class ContextBudget:
    def __init__(self, total: int, reserve: int):
        self.total = total
        self.reserve = reserve
        self.used = 0

    @property
    def remaining(self) -> int:
        return max(0, self.total - self.used - self.reserve)

    def fits(self, tokens: int) -> bool:
        return tokens <= self.remaining

    def spend(self, tokens: int) -> None:
        self.used += tokens

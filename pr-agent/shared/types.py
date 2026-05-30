"""Shared types used across versions and the eval harness.

Keep this file tiny and dependency-free; every version imports from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Severity = Literal["must", "should", "suggestion"]


@dataclass
class Finding:
    """One issue emitted by a reviewer version.

    Versions emit Findings; the eval harness scores them against ground truth.
    The shape is deliberately minimal — extra metadata each version wants to
    keep can live in `extra`.
    """

    file: str                       # path relative to the repo root (matches PR-diff paths)
    line_start: int
    line_end: int
    category: str                   # security | performance | dry | kiss | quality | test | standards | correctness | other
    severity: Severity
    title: str                      # short headline (<= ~80 chars)
    message: str                    # full prose body (can be multi-line)
    source: str = "generalist"      # which agent emitted it (specialist name, "tier1", "generalist", etc.)
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "file": self.file,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "category": self.category,
            "severity": self.severity,
            "title": self.title,
            "message": self.message,
            "source": self.source,
            "extra": self.extra,
        }

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class StageTwoReviewResult:
    extracted_text: str
    route_outcome: str
    route_reason: str | None
    route_subtype: str | None
    extraction_trace: tuple[str, ...] = ()
    route_trace: tuple[str, ...] = ()
    derived_payload: dict[str, Any] | None = None

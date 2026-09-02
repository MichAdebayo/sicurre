"""A monthly release must survive regenerating its own back catalogue.

The generation lanes are deterministic: the same seeds produce the same texts.
So the second release reproduces everything the first one wrote, and every one
of those texts collides with the unique index on
data_normalized_message.text_sha256.

On 1 September this took the scheduled release down twice. First as a hard
ValueError from the promotion guard, before anything was written. Then, once
that was filtered, as an IntegrityError mid-INSERT - after earlier lanes had
already committed, leaving a half-finished release, which is worse than one
that never started.
"""

from __future__ import annotations

from hashlib import sha256
from typing import Any

import pytest

from data_platform.services.shared.review_persistence import ReviewPersistenceService


def _sha(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


class _Result:
    def __init__(self, rows: list[tuple[str]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[str]]:
        return self._rows


class _Session:
    """Stands in for the DB: returns whichever hashes are already curated."""

    def __init__(self, curated: set[str]) -> None:
        self.curated = curated

    async def execute(self, _statement: Any) -> _Result:
        return _Result([(h,) for h in self.curated])


def _sample(draft_id: str, text: str) -> dict[str, Any]:
    return {
        "draft_id": draft_id,
        "variant_index": 0,
        "normalized_text": text,
        "text_sha256": _sha(text),
    }


@pytest.mark.asyncio
async def test_already_curated_texts_are_dropped() -> None:
    old, new = "Objet : deja vu\n\ncorps", "Objet : inedit\n\ncorps"
    kept, skipped = await ReviewPersistenceService._drop_already_curated(
        _Session({_sha(old)}), [_sample("d1", old), _sample("d2", new)], {}
    )

    assert skipped == 1
    assert [s["draft_id"] for s in kept] == ["d2"]


@pytest.mark.asyncio
async def test_a_text_repeated_inside_one_batch_is_kept_once() -> None:
    """Two lanes in one run can synthesise the same text from the same seeds.

    Both pass the already-curated check, because neither is in the database
    yet; the collision then happens inside the INSERT.
    """
    text = "Objet : genere deux fois\n\ncorps"
    kept, skipped = await ReviewPersistenceService._drop_already_curated(
        _Session(set()),
        [_sample("d1", text), _sample("d2", text), _sample("d3", "Objet : autre\n\ncorps")],
        {},
    )

    assert skipped == 1
    assert len(kept) == 2
    assert len({s["text_sha256"] for s in kept}) == 2


@pytest.mark.asyncio
async def test_a_wholly_regenerated_batch_drops_to_empty_without_raising() -> None:
    """The realistic second-release case: nothing new at all.

    This must be an empty promotion, not an exception - the release has to
    continue to the lanes that do have new material.
    """
    texts = [f"Objet : lot {i}\n\ncorps" for i in range(4)]
    kept, skipped = await ReviewPersistenceService._drop_already_curated(
        _Session({_sha(t) for t in texts}),
        [_sample(f"d{i}", t) for i, t in enumerate(texts)],
        {},
    )

    assert kept == []
    assert skipped == 4


@pytest.mark.asyncio
async def test_a_fresh_batch_is_passed_through_untouched() -> None:
    samples = [_sample("d1", "Objet : un\n\ncorps"), _sample("d2", "Objet : deux\n\ncorps")]
    kept, skipped = await ReviewPersistenceService._drop_already_curated(
        _Session(set()), samples, {}
    )

    assert skipped == 0
    assert kept == samples


@pytest.mark.asyncio
async def test_a_sample_with_no_text_is_left_for_the_downstream_guard() -> None:
    """persist_generated_promotion_review rejects it with a clearer message."""
    empty: dict[str, Any] = {"draft_id": "d1", "variant_index": 0}
    kept, skipped = await ReviewPersistenceService._drop_already_curated(
        _Session(set()), [empty], {}
    )

    assert kept == [empty]
    assert skipped == 0


# ── The second write path ────────────────────────────────────────────────────
# Common Crawl acceptance builds normalized-message rows directly rather than
# going through gated promotion. It reaches the same unique index, so filtering
# only the promotion path still lets the release die mid-INSERT.


def _cc_pair(candidate_id: str, text: str) -> tuple[dict[str, Any], dict[str, Any]]:
    return (
        {"candidate_id": candidate_id},
        {"raw_record_id": candidate_id, "text_sha256": _sha(text), "normalized_text": text},
    )


@pytest.mark.asyncio
async def test_cc_already_curated_candidates_are_dropped() -> None:
    old, new = "Objet : deja curated\n\ncorps", "Objet : nouveau\n\ncorps"
    (c1, m1), (c2, m2) = _cc_pair("a", old), _cc_pair("b", new)

    kept_c, kept_m, skipped = (
        await ReviewPersistenceService._drop_duplicate_cc_candidates(
            _Session({_sha(old)}), [c1, c2], [m1, m2]
        )
    )

    assert skipped == 1
    assert [c["candidate_id"] for c in kept_c] == ["b"]
    assert [m["raw_record_id"] for m in kept_m] == ["b"]


@pytest.mark.asyncio
async def test_cc_filter_keeps_the_two_lists_aligned() -> None:
    """They are consumed by `zip(..., strict=True)`.

    Dropping from one list and not the other pairs each candidate with the
    wrong message - which would mislabel rows rather than fail loudly.
    """
    pairs = [_cc_pair(str(i), f"Objet : {i}\n\ncorps") for i in range(5)]
    curated = {_sha("Objet : 1\n\ncorps"), _sha("Objet : 3\n\ncorps")}

    kept_c, kept_m, skipped = (
        await ReviewPersistenceService._drop_duplicate_cc_candidates(
            _Session(curated), [c for c, _ in pairs], [m for _, m in pairs]
        )
    )

    assert skipped == 2
    assert len(kept_c) == len(kept_m) == 3
    for candidate, message in zip(kept_c, kept_m, strict=True):
        assert candidate["candidate_id"] == message["raw_record_id"], "pairing shifted"


@pytest.mark.asyncio
async def test_cc_repeated_text_inside_one_batch_is_kept_once() -> None:
    text = "Objet : repete\n\ncorps"
    (c1, m1), (c2, m2) = _cc_pair("a", text), _cc_pair("b", text)

    kept_c, kept_m, skipped = (
        await ReviewPersistenceService._drop_duplicate_cc_candidates(
            _Session(set()), [c1, c2], [m1, m2]
        )
    )

    assert skipped == 1
    assert len(kept_c) == len(kept_m) == 1

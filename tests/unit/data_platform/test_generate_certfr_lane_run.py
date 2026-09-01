"""`generate.py --mode certfr` must actually load CTI and persist drafts.

The CERT-FR services were unit-tested individually and none of them ran: the
router sent records to a destination with no caller. `_run_certfr_generation`
is that caller, so a test that only exercises the lane's pure functions would
repeat the original mistake one level up.
"""

from __future__ import annotations

import argparse
import json
from types import SimpleNamespace
from typing import Any

import pytest

from data_platform.cli.datasets import generate

CTI_REPORT = (
    "ANSSI - CERT-FR  TLP:CLEAR  Table des matieres. "
    "Panorama de la cybermenace. Le CERT-FR a observe une campagne de hameconnage "
    "bancaire ciblant les clients francais par courriel. Les messages usurpent "
    "l identite d une banque et demandent la confirmation des coordonnees "
    "bancaires et du RIB. Domaines malveillants: bnp-verif.top. "
    "Adresses: alerte@bnp-verif.top. IP: 192.0.2.10"
)


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def scalars(self) -> _Result:
        return self

    def all(self) -> list[Any]:
        return self._rows


class _Session:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.executed = 0

    async def execute(self, _statement: Any) -> _Result:
        self.executed += 1
        return _Result(self._rows)


def _args() -> argparse.Namespace:
    return argparse.Namespace(
        run_timestamp="2026-09-01T00:00:00Z",
        pipeline_version="test",
        persist_lineage=True,
    )


def _record(raw_content: str, record_id: str = "r1") -> SimpleNamespace:
    return SimpleNamespace(id=record_id, raw_content=raw_content)


@pytest.mark.asyncio
async def test_cti_records_become_persisted_drafts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    persisted: dict[str, Any] = {}

    async def _fake_persist(_session: Any, **kwargs: Any) -> dict[str, object]:
        persisted.update(kwargs)
        return {"written": True}

    monkeypatch.setattr(generate, "_persist_bundle", _fake_persist)
    session = _Session([_record(json.dumps({"text": CTI_REPORT}))])

    out = await generate._run_certfr_generation(session, _args())

    assert out["cti_records"] == 1
    assert out["generated_count"] >= 1
    assert out["persistence"] == {"written": True}
    # The lane must hand persistence the bundle, not raw records.
    assert persisted["payload"]["samples"]
    assert persisted["pipeline_version"] == "test"


@pytest.mark.asyncio
async def test_unparseable_raw_content_is_skipped_not_fatal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One malformed row must not abort the whole monthly release."""

    async def _fake_persist(_session: Any, **_kwargs: Any) -> dict[str, object]:
        return {"written": True}

    monkeypatch.setattr(generate, "_persist_bundle", _fake_persist)
    session = _Session(
        [
            _record("this is not json", "bad"),
            _record(json.dumps({"text": CTI_REPORT}), "good"),
        ]
    )

    out = await generate._run_certfr_generation(session, _args())

    assert out["cti_records"] == 1, "the malformed row should be dropped, the good one kept"


@pytest.mark.asyncio
async def test_no_cti_records_persists_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty month must be a clean no-op, not an empty write."""
    called = False

    async def _fake_persist(_session: Any, **_kwargs: Any) -> dict[str, object]:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(generate, "_persist_bundle", _fake_persist)
    session = _Session([])

    out = await generate._run_certfr_generation(session, _args())

    assert out["cti_records"] == 0
    assert out["generated_count"] == 0
    assert out["persistence"] is None
    assert not called, "persistence must not be invoked with no drafts"

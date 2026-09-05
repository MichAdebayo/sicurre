"""The Worker has one source, and re-provisioning must not disarm it.

Two copies of the script existed: this one, and an inline string in the
provisioner that never gained the reporting branches. The provisioner deployed
the inline copy, so every re-provision reverted DMARC and reported-email
ingestion to plain classification. Cloudflare also replaces the whole binding
set on each deploy, so a binding omitted from the metadata is deleted from the
running Worker - which turns ingestion off just as effectively.
"""

from __future__ import annotations

from pathlib import Path

from data_platform.services import cloudflare_provisioner as provisioner

ASSET = (
    Path(provisioner.__file__).parent / "assets" / "email_gateway_worker.js"
)


def test_the_deployed_script_is_the_packaged_asset() -> None:
    """No second copy: what ships is what the repository holds."""
    assert provisioner._WORKER_JS == ASSET.read_text(encoding="utf-8")


def test_the_repository_holds_exactly_one_worker_script() -> None:
    """A stray copy under deploy/ is what drifted the first time."""
    root = Path(provisioner.__file__).parents[3]
    copies = [
        p for p in root.rglob("*worker*.js")
        if "node_modules" not in p.parts and ".venv" not in p.parts
    ]
    assert copies == [ASSET], f"expected only {ASSET}, found {copies}"


def test_the_script_keeps_its_reporting_branches() -> None:
    """Losing these silently converts machine reports into scanned mail."""
    script = provisioner._WORKER_JS
    assert "dmarc@sicurre.com" in script
    assert "/v1/email/dmarc-reports" in script
    assert "REPORT_ADDRESS" in script
    assert "SICURRE_REPORTED_EMAIL_INGEST_KEY" in script


def test_a_failed_ingest_forwards_instead_of_classifying() -> None:
    """A DMARC report was quarantined as phishing because it fell through."""
    script = provisioner._WORKER_JS
    dmarc_branch = script.split("dmarc@sicurre.com")[2]
    up_to_scan = dmarc_branch.split("SICURRE_SCAN_URL")[0]
    assert "message.forward" in up_to_scan, (
        "the dmarc branch must forward and return; falling through reaches the "
        "classifier, which is what quarantined a Google report as phishing"
    )


def test_deploy_sends_the_ingest_key_binding(monkeypatch) -> None:
    """Cloudflare replaces bindings wholesale; omitting this deletes it."""
    import asyncio
    import json

    captured: dict = {}

    class _Response:
        status_code = 200
        is_success = True
        text = ""

        @staticmethod
        def json() -> dict:
            return {"success": True, "result": {}}

    class _Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_exc) -> None:
            return None

        async def put(self, _url, headers=None, files=None):
            captured["metadata"] = json.loads(files["metadata"][1])
            return _Response()

    monkeypatch.setattr(provisioner.httpx, "AsyncClient", lambda **_kw: _Client())

    client = provisioner.CloudflareProvisioner(api_token="t")
    asyncio.run(
        client.deploy_email_worker(
            account_id="acct",
            worker_name="w",
            scan_url="https://example.test/v1/email/scan",
            shared_secret="s",
            forward_to="to@example.test",
            reported_email_ingest_key="ingest-key",
        )
    )

    names = {b["name"] for b in captured["metadata"]["bindings"]}
    assert "SICURRE_REPORTED_EMAIL_INGEST_KEY" in names
    assert {"SICURRE_SCAN_URL", "SICURRE_SHARED_SECRET", "FORWARD_TO"} <= names

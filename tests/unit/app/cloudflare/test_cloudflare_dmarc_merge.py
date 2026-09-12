from data_platform.services.dns_records import merge_dmarc


def test_merge_dmarc_adds_sicurre_reporting_destination_once() -> None:
    record = "v=DMARC1; p=reject; rua=mailto:michael@vinse.app"

    merged = merge_dmarc(record)

    assert merged == "v=DMARC1; p=reject; rua=mailto:michael@vinse.app,mailto:dmarc@sicurre.com"


def test_merge_dmarc_is_idempotent_for_sicurre_reporting_destination() -> None:
    record = "v=DMARC1; p=reject; rua=mailto:michael@vinse.app,mailto:dmarc@sicurre.com"

    merged_once = merge_dmarc(record)
    merged_twice = merge_dmarc(merged_once)

    assert merged_once == merged_twice
    assert merged_twice.count("dmarc@sicurre.com") == 1


def test_merge_dmarc_creates_reject_policy_when_missing() -> None:
    assert merge_dmarc("") == "v=DMARC1; p=reject; rua=mailto:dmarc@sicurre.com"

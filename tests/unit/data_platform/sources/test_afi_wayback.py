from __future__ import annotations

from data_platform.extractors.afi_wayback import AFIWaybackExtractor


def test_parse_inventory_payload_filters_duplicates_and_reply_urls() -> None:
    payload = "\n".join(
        [
            "20240101000000 https://antifraudintl.org/threads/madame-heritage.123/ 200",
            "20240101010000 https://antifraudintl.org/threads/madame-heritage.123/reply 200",
            "20240101020000 https://antifraudintl.org/threads/madame-heritage.123/ 200",
            "20240101030000 https://antifraudintl.org/forums/general.1/ 200",
        ]
    )

    records = AFIWaybackExtractor.parse_inventory_payload(payload)

    assert len(records) == 1
    assert records[0]["thread_id"] == "123"
    assert records[0]["slug_lang"] == "fr_likely"


def test_extract_content_returns_title_and_long_messages() -> None:
    html = """
    <html>
      <head><title>Madame Héritage | antifraudintl.org</title></head>
      <body>
        <div class="bbWrapper">Bonjour Monsieur, je vous contacte pour votre héritage en banque internationale.</div>
        <div class="bbWrapper">Court</div>
      </body>
    </html>
    """

    title, messages = AFIWaybackExtractor.extract_content(html)

    assert title == "Madame Héritage"
    assert len(messages) == 1
    assert "héritage" in messages[0]


def test_detect_french_requires_multiple_markers() -> None:
    assert AFIWaybackExtractor.detect_french(
        "Bonjour Monsieur, merci de contacter votre banque pour le transfert."
    )
    assert not AFIWaybackExtractor.detect_french(
        "Hello there, please confirm your account immediately."
    )

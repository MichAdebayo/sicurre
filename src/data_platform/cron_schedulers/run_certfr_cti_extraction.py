"""Run the CERT-FR CTI content extraction job.

Usage::

    cd backend && uv run --group backend python scripts/run_certfr_cti_extraction.py

Designed to be called bi-weekly by a scheduler (cron / Cloud Scheduler).
Most runs will find zero new reports and exit in under two seconds.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[3]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from core.database import AsyncSessionFactory
from data_platform.extractors.certfr_cti import (
    CertFRCtiExtractor,
)


async def main() -> None:
    extractor = CertFRCtiExtractor()

    async with AsyncSessionFactory() as session:
        result = await extractor.run(session, trigger_mode="scheduled")

    print(result.log_message or "CERT-FR CTI extraction completed")
    print(
        f"  discovered={result.discovered_count}"
        f"  new={result.new_count}"
        f"  extracted={result.extracted_count}"
        f"  skipped={result.skipped_count}"
        f"  failed={result.failed_count}"
    )
    if result.reports:
        for report in result.reports:
            status = "📄 PDF" if report.extraction_method == "pdfplumber" else "🌐 HTML"
            phishing = "🎣" if report.is_phishing_related else "—"
            print(
                f"  {status} {report.reference}: "
                f"{report.text_length} chars, "
                f"{len(report.domains)}d/{len(report.emails)}e/"
                f"{len(report.ips)}i/{len(report.hashes)}h "
                f"phishing={phishing}"
            )


if __name__ == "__main__":
    asyncio.run(main())

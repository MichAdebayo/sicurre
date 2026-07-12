import sys
from pathlib import Path
import pytest
import os

sys.path.insert(0, str(Path("src").resolve()))
from data_platform.extractors.incremental_cc_extractor import DURATION_MAP

@pytest.mark.e2e
@pytest.mark.skip(reason="Requires external network and takes time")
@pytest.mark.asyncio
async def test_cc_cron():
    DURATION_MAP["short"] = 60  # 60 seconds
    from data_platform.cron_schedulers.bigdata.run_incremental_cc import run_incremental_cc_cron
    os.environ["SICURRE_CC_CRON_DURATION_MODE"] = "short"
    await run_incremental_cc_cron()

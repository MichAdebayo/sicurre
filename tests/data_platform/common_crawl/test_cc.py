import sys
from pathlib import Path
sys.path.insert(0, str(Path("src").resolve()))
from data_platform.extractors.incremental_cc_extractor import DURATION_MAP
DURATION_MAP["short"] = 60  # 60 seconds
from data_platform.cron_schedulers.bigdata.run_incremental_cc import run_incremental_cc_cron
import asyncio
import os
os.environ["SICURRE_CC_CRON_DURATION_MODE"] = "short"
asyncio.run(run_incremental_cc_cron())

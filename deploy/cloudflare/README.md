# Cloudflare Email Worker

The gateway Worker script is **not** kept here. It lives at

    src/data_platform/services/assets/email_gateway_worker.js

and `CloudflareProvisioner.deploy_email_worker` reads that file when it
provisions a domain. It sits under `src/` because that is what the container
image copies; a second copy here drifted from the deployed one and silently
removed DMARC and reported-email ingestion.

Edit that file, never a copy. `tests/unit/app/test_email_gateway_worker.py`
fails if the reporting branches or their binding go missing.

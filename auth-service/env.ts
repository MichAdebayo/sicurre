import path from "node:path";

import { config as loadEnv } from "dotenv";

// Compose injects production variables; this file is only a quiet local fallback.
loadEnv({ path: path.resolve(process.cwd(), ".env"), quiet: true });

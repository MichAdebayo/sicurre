/**
 * Dedicated Email Routing Worker for report+<workspace-token>@sicurre.com.
 *
 * Bind SICURRE_API_URL and SICURRE_REPORTED_EMAIL_INGEST_KEY as Worker secrets.
 * Configure the sicurre.com catch-all route to invoke this Worker.
 */
export default {
  async email(message, env) {
    const recipient = message.to.toLowerCase();
    const apiBase = env.SICURRE_API_URL.replace(/\/$/, "");
    if (recipient === "dmarc@sicurre.com") {
      const response = await fetch(`${apiBase}/v1/email/dmarc-reports`, {
        method: "POST",
        headers: {
          "Content-Type": "message/rfc822",
          "X-Sicurre-Report-Key": env.SICURRE_REPORTED_EMAIL_INGEST_KEY,
        },
        body: await new Response(message.raw).arrayBuffer(),
      });
      if (!response.ok) {
        throw new Error(`Sicurre DMARC ingestion failed (${response.status})`);
      }
      return;
    }

    const match = /^report\+([a-z0-9_-]{22}\.[a-z0-9_-]{22})@sicurre\.com$/i.exec(recipient);
    if (!match) {
      message.setReject("Unknown Sicurre reporting address");
      return;
    }

    const response = await fetch(
      `${apiBase}/v1/email/reports/${match[1]}`,
      {
        method: "POST",
        headers: {
          "Content-Type": "message/rfc822",
          "X-Sicurre-Report-Key": env.SICURRE_REPORTED_EMAIL_INGEST_KEY,
        },
        body: await new Response(message.raw).arrayBuffer(),
      },
    );
    if (!response.ok) {
      throw new Error(`Sicurre report ingestion failed (${response.status})`);
    }
  },
};

/**
 * Sicurre Email Gateway Worker
 *
 * Handles every address that reaches the sicurre.com catch-all:
 *
 *   dmarc@sicurre.com            -> POST /v1/email/dmarc-reports
 *   report+<token>@sicurre.com   -> POST /v1/email/reports/<token>
 *   everything else              -> scan, quarantine or forward
 *
 * The reporting addresses used to live in a second Worker that was never
 * deployed, so DMARC aggregate reports and forwarded user reports both fell
 * through to the gateway, were scanned as ordinary mail and forwarded to the
 * destination inbox. Nothing ingested them. Cloudflare Email Routing matches
 * only literal addresses or the catch-all, and report+<token> carries a dynamic
 * token, so a routing rule cannot express it - the catch-all Worker has to.
 *
 * Ingestion is deliberately fail-open. If the ingest key is absent, or the API
 * rejects or is unreachable, the report is forwarded instead of throwing. A
 * failed ingestion should cost a report, never the mail - and never be handed
 * to the classifier, which would turn a machine report into a false threat.
 *
 * Bindings: SICURRE_SCAN_URL, SICURRE_SHARED_SECRET, FORWARD_TO,
 *           SICURRE_REPORTED_EMAIL_INGEST_KEY (optional; enables ingestion).
 */

const REPORT_ADDRESS = /^report\+([a-z0-9_-]{22}\.[a-z0-9_-]{22})@sicurre\.com$/i;

/** Derive the API origin from the configured scan URL. */
function apiBase(env) {
  return env.SICURRE_SCAN_URL.replace(/\/v1\/email\/scan\/?$/, "").replace(/\/$/, "");
}

/** POST a raw message to an ingest endpoint. Returns true only on success. */
async function ingest(env, path, rawBytes) {
  if (!env.SICURRE_REPORTED_EMAIL_INGEST_KEY) return false;
  try {
    const response = await fetch(`${apiBase(env)}${path}`, {
      method: "POST",
      headers: {
        "Content-Type": "message/rfc822",
        "X-Sicurre-Report-Key": env.SICURRE_REPORTED_EMAIL_INGEST_KEY,
      },
      body: rawBytes,
      signal: AbortSignal.timeout(15_000),
    });
    return response.ok;
  } catch (_) {
    return false;
  }
}

export default {
  async email(message, env, _ctx) {
    const from      = message.from || '';
    const recipient = (message.to || '').toLowerCase();
    const subject   = message.headers.get('subject') || message.headers.get('Subject') || '';

    // Read the original MIME once. Only a short text projection is classified.
    let rawBytes = new ArrayBuffer(0);
    let bodyText = '';
    try {
      rawBytes = await new Response(message.raw).arrayBuffer();
      const rawText = new TextDecoder('utf-8', { fatal: false }).decode(rawBytes);
      bodyText = rawText
        .replace(/--[A-Za-z0-9_\-\.]+(?:--)?/g, '')
        .replace(/Content-[^\n]+\n/g, '')
        .replace(/\r\n\r\n/g, '\n\n')
        .trim()
        .slice(0, 5_500);
    } catch (_) { /* fail-open body read */ }

    // -- Reporting addresses, never classified -------------------------------
    // These carry machine reports, not mail a person sent. Classifying one on a
    // failed ingest quarantined a Google DMARC report as phishing and alerted
    // the customer, so a failed ingest now forwards the report untouched rather
    // than handing it to the classifier.
    if (recipient === 'dmarc@sicurre.com') {
      if (rawBytes.byteLength && await ingest(env, '/v1/email/dmarc-reports', rawBytes)) return;
      await message.forward(env.FORWARD_TO);
      return;
    }
    const reportMatch = REPORT_ADDRESS.exec(recipient);
    if (reportMatch) {
      if (rawBytes.byteLength && await ingest(env, `/v1/email/reports/${reportMatch[1]}`, rawBytes)) return;
      await message.forward(env.FORWARD_TO);
      return;
    }

    const headerMessageId = message.headers.get('message-id') || message.headers.get('Message-ID') || '';
    let messageId = headerMessageId.trim();
    if (!messageId && rawBytes.byteLength) {
      const digest = await crypto.subtle.digest('SHA-256', rawBytes);
      messageId = Array.from(new Uint8Array(digest), b => b.toString(16).padStart(2, '0')).join('');
    }

    // -- Call Sicurre scan endpoint ------------------------------------------
    let verdict = 'safe';
    let scanStatus = 'unavailable';
    let confidence = '';
    let scanHttpStatus = '';
    let quarantineId = '';
    let eventId = '';
    try {
      const resp = await fetch(env.SICURRE_SCAN_URL, {
        method : 'POST',
        headers: {
          'Content-Type'     : 'application/json',
          'X-Sicurre-Secret' : env.SICURRE_SHARED_SECRET,
        },
        body  : JSON.stringify({
          message_id     : messageId,
          subject,
          sender         : from,
          text           : bodyText,
          use_llm        : true,
          use_virustotal : false,
        }),
        signal: AbortSignal.timeout(10_000),
      });
      scanHttpStatus = String(resp.status);
      if (resp.ok) {
        const data = await resp.json();
        verdict = (data.verdict || 'safe').toLowerCase();
        scanStatus = 'scanned';
        confidence = data.score === undefined ? '' : String(data.score);
        quarantineId = data.quarantine_id ? String(data.quarantine_id) : '';
        eventId = data.event_id ? String(data.event_id) : '';
      } else {
        scanStatus = 'api-error';
      }
    } catch (_) {
      scanStatus = 'api-unreachable';
    }

    if (verdict === 'phishing') {
      message.setReject('Phishing email blocked by Sicurre Anti-Phishing Gateway');
      return;
    }

    if (verdict === 'quarantine') {
      if (!quarantineId || !rawBytes.byteLength) {
        message.setReject('Sicurre quarantine storage unavailable; message was not discarded');
        return;
      }
      const uploadUrl = env.SICURRE_SCAN_URL.replace(/\/v1\/email\/scan\/?$/, `/v1/email/quarantine/${quarantineId}/content`);
      try {
        const upload = await fetch(uploadUrl, {
          method: 'PUT',
          headers: {
            'Content-Type': 'message/rfc822',
            'X-Sicurre-Secret': env.SICURRE_SHARED_SECRET,
          },
          body: rawBytes,
          signal: AbortSignal.timeout(15_000),
        });
        if (!upload.ok) {
          message.setReject('Sicurre quarantine storage failed; message was not discarded');
        }
      } catch (_) {
        message.setReject('Sicurre quarantine storage unreachable; message was not discarded');
      }
      return;
    }

    const traceHeaders = new Headers();
    traceHeaders.set('X-Sicurre-Gateway', 'cloudflare-email-worker');
    traceHeaders.set('X-Sicurre-Scan-Status', scanStatus);
    traceHeaders.set('X-Sicurre-Verdict', verdict);
    traceHeaders.set('X-Sicurre-Scan-Http-Status', scanHttpStatus);
    traceHeaders.set('X-Sicurre-Confidence', confidence);
    traceHeaders.set('X-Sicurre-Event-ID', eventId);
    await message.forward(env.FORWARD_TO, traceHeaders);
  },
};

# SLOs and SLIs

## SLIs (what we measure)
- Availability of `/health`
- p95 latency of `/v1/classify`
- End-to-end classification/quarantine time from Cloudflare Worker delivery
- Error rate (5xx / total)
- Duplicate Worker deliveries handled (count)
- Feedback submission success rate

## SLOs (targets)
- Availability: 99.5% monthly
- `/v1/classify` p95 latency: < 200ms
- End-to-end classification/quarantine p95: < 5s
- Error rate: < 1% daily

## Error budget policy
If error budget is breached:
- Freeze new feature releases
- Focus on reliability and incident prevention

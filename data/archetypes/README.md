# Email Archetypes for Synthetic Generation

This directory contains archetype template files used to generate synthetic training data
for the 3-class CamemBERTav2 classifier (phishing=0, spam=1, legitimate=2).

## Structure

- `phishing_archetypes.json` — Phishing email templates (3 tiers: simple/medium/hard)
- `spam_archetypes.json` — Spam email templates (3 tiers)
- `legitimate_archetypes.json` — Legitimate email templates (3 tiers)

## Tier Distribution (per class)
- Simple: 30% — easy to classify, obvious signals
- Medium: 40% — moderate difficulty, brand impersonation / borderline
- Hard: 30% — deceptive, looks like another class

## Sources
- Real FR phishing collected from personal inboxes (Dassault Aviation, Vinci, Parkside)
- 87 French spam from FredZhang7/all-scam-spam
- EN spam patterns adapted to French context
- Existing adapted/synthetic phishing archetypes (AFI, CERT-FR, SAP Labs)
- Legitimate SaaS marketing patterns adapted to French brands

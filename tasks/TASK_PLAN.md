# Titre Dev IA: Bloc-by-Bloc Task Checklist for Sicurre
**Complete Competency Requirements Mapped to Project Tasks**

> ⚠️ **Brand Note:** The name "InboxSentinel" is taken (inboxsentinel.ai — generic English SaaS, no real AI differentiation). This product is now branded **Sicurre** — a French-native name (vigil = surveillance), targeting France's 3.8M auto-entrepreneurs and Francophone African SMBs.

---

## Executive Summary

This document maps **every competency** in the Titre Développeur en Intelligence Artificielle (Dev IA) to **specific deliverables** for Sicurre. Each task includes acceptance criteria, tools, and estimated timeline to ensure you tick off all requirements for your defence.

---

## Sicurre: Sharpened Product Identity

### What Sicurre Is
Sicurre is a **French-native, real-time phishing detection and inbox remediation system** that automatically removes phishing emails from Gmail and M365 inboxes within 2 seconds of arrival — using a fine-tuned CamemBERTv2 model trained specifically on French-language phishing patterns (URSSAF, DGFiP, CAF, Ameli impersonation).

### Why "InboxSentinel.ai" Is Not a Threat
The site at inboxsentinel.ai is a generic English-language SaaS with minimal AI depth — it appears to be an off-the-shelf spam filter with a marketing layer. It does not:
- Have a French-language model
- Target French auto-entrepreneurs or Francophone Africa
- Offer attack-chain correlation (email → voice → video)
- Publish open-source model weights

Sicurre's differentiation is language-specific, geography-specific, and technically deeper.

### Target Market (ICP — Ideal Customer Profile)

**Primary: French auto-entrepreneurs and TPEs (0–9 employees)**
- France has **3.8 million auto-entrepreneurs** — all solo, no IT team
- They receive French administrative phishing that no English-trained system catches
- Specific pain: *"Je reçois des emails de l'URSSAF que je ne sais pas si c'est vrai ou du phishing."*
- Willingness to pay: €5–15/month (cost of one coffee/week)
- Cultural preference: trust "made in France" tools over US SaaS

**Secondary: Francophone African SMBs (Senegal, Côte d'Ivoire, Cameroon, Mali)**
- WhatsApp + email-first business communication
- Growing digital economy, rising fraud rates
- **Zero local competitors** — no French-language protection exists here
- Price point: $2–5/month (high volume, lower individual spend)

**NOT targeting (explicitly out of scope):**

| Segment | Reason to Exclude |
|---------|------------------|
| French enterprises (500+ employees) | Darktrace, Blokkus, Proofpoint already serve them |
| English-speaking SMBs | InboxSentinel.ai, others — overcrowded |
| Government/public sector | Impossible procurement cycles for solo dev |
| End consumers (non-professional Gmail) | Low willingness to pay, hard to monetize |

---

## Open-Source vs. Paid: The Definitive Plan

This was a contradiction in earlier documents. Here is the resolved, definitive strategy:

### The Open-Core Model

Sicurre uses a **dual-track architecture** — identical to how MongoDB, Grafana, Elastic, and Redis operate:

**🟢 Open-Source (Free Forever)**
- The **fine-tuned CamemBERTv2 model weights** are published publicly on HuggingFace Hub:
  `Sicurre/camembertv2-phishing-fr`
- Anyone can download, audit, and run the model locally — no charge, no restriction
- **Why open-source the model?**
  - Builds trust — jury and users can audit classification decisions (no black box)
  - Attracts contributors to expand the French phishing corpus
  - Positions Sicurre as thought leader in French cybersecurity
  - Strengthens your defence: transparency is a technical and ethical argument
  - Mirrors how your LyScout model already lives on HuggingFace

**💰 Paid (The SaaS Product)**
- The *application layer* that wraps the model is a paid subscription:
  - Gmail/M365 OAuth integration + real-time Pub/Sub listener
  - Automatic inbox remediation (trash phishing within 2s)
  - React dashboard (threat log, statistics, audit trail)
  - Continuous model retraining on new French phishing IOCs (CERT-FR feeds)
  - DMARC/SPF/DKIM validation layer
  - Attack-chain correlation (Phase 2)

**Why this is not a contradiction — it's standard industry practice:**
> "The model is free. The *managed service* is paid. You could build this yourself from our GitHub — but we save you 200 hours of engineering and update the model weekly."

| Component | Open-Source | Paid |
|-----------|-------------|------|
| CamemBERTv2 fine-tuned weights | ✅ Public HuggingFace | — |
| Training code + scripts | ✅ Public GitHub | — |
| Gmail/M365 integration app | — | ✅ €5–15/month |
| Real-time inbox remediation | — | ✅ |
| Dashboard + audit log | — | ✅ |
| Weekly model retraining | — | ✅ |
| Priority support | — | ✅ Business tier |

### Pricing Tiers

| Tier | Price | Limit | Target User |
|------|-------|-------|-------------|
| **Free** | €0/month | 10 emails/day | Students, testing |
| **Pro** | €5/month | Unlimited, 1 inbox | French auto-entrepreneurs |
| **Business** | €15/month | Unlimited, 5 inboxes + API | TPEs (2–9 employees) |

**Unit economics (solo dev):**
- Infrastructure cost per user: ~€0.20/month (Cloud Run serverless)
- Pro tier gross margin: **96%** (€4.80 net per user)
- Break-even: **21 paying users**
- Year 1 target: 200 users → €1,000/month → **€12,000 ARR**

---

## How to Use This Document

**Structure:** 3 Blocs → 21 Competencies (C1-C21) → Concrete Tasks

**For each competency:**
- ✅ **Task**: What you need to build/document
- 📋 **Deliverable**: Physical output for defence portfolio
- 🔧 **Tools**: Technologies/frameworks to use
- ⏱️ **Timeline**: Estimated effort
- ✔️ **Acceptance Criteria**: How jury evaluates it

**Evaluation format:**
- **E1**: Written professional report + oral defence (Bloc 1)
- **E2**: Case study — veille + benchmark (Bloc 2)
- **E3**: Project demonstration + report (Bloc 2)
- **E4**: Project demonstration + report (Bloc 3)
- **E5**: Monitoring case study (Bloc 3)

---

# BLOC 1: Data Collection, Storage & Provisioning

**Evaluation:** E1 (Professional Report + Oral Defence)

**Project Context:** Build a complete data pipeline to collect French phishing emails from multiple sources (CERT-FR, PhishTank, Signal-Spam, synthetic LLM generation), clean/aggregate them, store in a RGPD-compliant PostgreSQL database, and expose via REST API. This pipeline directly feeds the CamemBERTv2 fine-tuning workflow and is your strongest Bloc 1 argument — **you are building a dataset that does not exist publicly**.

---

## C1: Automate Data Extraction from Multiple Sources

### Task 1.1: Scrape PhishTank API for French Phishing URLs
✅ **What to do:**
- Write Python script using `requests` library
- Filter for `.fr` domains and French keywords (URSSAF, Ameli, impots, etc.)
- Parse JSON response and extract URLs, submission dates, verification status
- Save to CSV: `phishtank_french.csv`

📋 **Deliverable:** `scripts/phishtank_scraper.py` + output CSV

🔧 **Tools:** Python, `requests`, `pandas`, Jupyter Notebook

⏱️ **Timeline:** 3-5 days

✔️ **Acceptance Criteria:**
- Script runs without errors
- Extracts 500+ French phishing URLs
- Code versioned on GitHub with commit history
- Documentation includes API authentication, rate limits

---

### Task 1.2: Scrape CERT-FR CTI Reports (Web Scraping)
✅ **What to do:**
- Use `BeautifulSoup` to crawl https://www.cert.ssi.gouv.fr/cti/
- Download PDF reports from 2020–2026
- Extract phishing indicators using `pdfplumber` (subject lines, domains, sender patterns)
- Structure as JSON: `cert_fr_phishing.json`

📋 **Deliverable:** `scripts/certfr_scraper.py` + JSON output

🔧 **Tools:** `BeautifulSoup`, `pdfplumber`, `requests`

⏱️ **Timeline:** 5-7 days

✔️ **Acceptance Criteria:**
- Successfully parses 50+ PDF reports
- Extracts structured phishing indicators in French
- Documented parsing logic (regex for French email patterns)

---

### Task 1.3: Generate Synthetic French Phishing Emails
✅ **What to do:**
- Use an LLM (Claude/GPT-4/Mistral) to generate realistic French phishing emails impersonating: URSSAF, DGFiP, CAF, Ameli, La Poste, Crédit Agricole, BNP Paribas
- Generate 2,000+ examples using templated prompts with variation
- Label as `phishing`, source as `synthetic`
- Save to CSV: `synthetic_french_phishing.csv`

📋 **Deliverable:** `scripts/synthetic_generator.py` + output CSV

🔧 **Tools:** OpenAI API or Mistral API, `pandas`

⏱️ **Timeline:** 3-5 days

✔️ **Acceptance Criteria:**
- 2,000+ synthetic examples generated
- Variety across entity types (URSSAF, CAF, DGFiP, banks)
- Formal "vous" register used throughout (reflecting real French phishing)

---

### Task 1.4: Read Local CSV Files (Legitimate Emails)
✅ **What to do:**
- Download legitimate French email sources (French mailing list archives, French open-source project lists)
- Read multiple CSV files using `pandas`
- Normalize column names (text, label, source)
- Combine into single dataframe

📋 **Deliverable:** `scripts/csv_reader.py`

🔧 **Tools:** `pandas`, `glob`

⏱️ **Timeline:** 2-3 days

✔️ **Acceptance Criteria:**
- Reads 3+ CSV files from different sources
- Handles encoding errors (UTF-8, ISO-8859-1 — critical for French accents)
- Combines into unified schema with label=0 (legitimate) / label=1 (phishing)

---

### Task 1.5: Connect to PostgreSQL Database
✅ **What to do:**
- Set up PostgreSQL database (Neon free tier for prod; SQLite for dev/CI)
- Write script to connect via `SQLAlchemy` / `SQLModel` (dialect-agnostic)
- Create tables for raw email data + metadata
- Execute test query to verify connection

📋 **Deliverable:** `scripts/db_connector.py` + SQL schema file

🔧 **Tools:** PostgreSQL (Neon), SQLite, `SQLAlchemy`, `psycopg2`

⏱️ **Timeline:** 2-3 days

✔️ **Acceptance Criteria:**
- Connection string parameterized via `.env` (not hardcoded)
- Error handling for connection failures
- Test query executes successfully

---

### Task 1.6: Programmatic Filtering/Parsing
✅ **What to do:**
- Parse HTML from scraped phishing pages (extract text from `<body>`)
- Language detection filter: keep only French samples (`langdetect` library)
- Extract relevant fields (subject, body, sender) from structured data

📋 **Deliverable:** `scripts/data_parser.py`

🔧 **Tools:** `BeautifulSoup`, `langdetect`, `re`

⏱️ **Timeline:** 3-4 days

✔️ **Acceptance Criteria:**
- Language detection filters out non-French samples (document % excluded)
- HTML → plain text preserves key content
- Handles malformed HTML gracefully

---

## C2: Develop SQL Queries for Data Extraction

### Task 2.1: Write SQL Extraction Queries
✅ **What to do:**
- Create SQL queries to extract phishing samples from PostgreSQL
- Examples:
  - `SELECT * FROM emails WHERE label=1 AND language='fr' ORDER BY created_at DESC LIMIT 1000`
  - `SELECT source, COUNT(*) FROM emails GROUP BY source` (distribution report)
- Optimize with indexes on `language`, `label`, `source` columns

📋 **Deliverable:** `sql/extraction_queries.sql` + documentation

🔧 **Tools:** PostgreSQL, DBeaver or pgAdmin

⏱️ **Timeline:** 2-3 days

✔️ **Acceptance Criteria:**
- Queries return correct result sets
- Execution time documented (`EXPLAIN ANALYZE`)
- Indexes applied — document before/after performance (e.g., 500ms → 50ms)

---

### Task 2.2: Document Query Optimization
✅ **What to do:**
- Explain JOIN type choices
- Document index creation decisions
- Show query performance metrics

📋 **Deliverable:** `docs/query_optimization.md`

⏱️ **Timeline:** 1-2 days

---

## C3: Aggregate and Clean Data

### Task 3.1: Aggregate Multi-Source Data
✅ **What to do:**
- Merge PhishTank, CERT-FR, synthetic, and legitimate CSV files into single dataset
- Standardize schema: `(text, label, source, language, timestamp)`
- Deduplicate using hash of first 300 chars (catches near-duplicates)
- Target: 6,000+ total samples (3,000 phishing + 3,000 legitimate), balanced

📋 **Deliverable:** `scripts/data_aggregator.py` + `french_phishing_dataset.csv`

🔧 **Tools:** `pandas`, `hashlib`

⏱️ **Timeline:** 3-5 days

✔️ **Acceptance Criteria:**
- All sources merged
- Duplicates removed (document count)
- Class balance documented (50/50 phishing/legitimate)

---

### Task 3.2: Remove Corrupted Entries
✅ **What to do:**
- Detect missing values, empty strings, bodies under 10 characters
- Remove rows where label is NaN (from your existing pipeline — use `normalize_label()` approach)
- Log removal statistics

📋 **Deliverable:** `scripts/data_cleaning.py` + cleaning report

🔧 **Tools:** `pandas`, `numpy`

⏱️ **Timeline:** 2-3 days

---

### Task 3.3: Normalize Data Formats
✅ **What to do:**
- Standardize date formats (ISO 8601)
- Normalize text encoding (all UTF-8 — critical for French accents: é, è, ç, à, ù)
- Labels: consistent `0` (legitimate) / `1` (phishing) — no mixing string/int formats

📋 **Deliverable:** `scripts/data_normalizer.py`

⏱️ **Timeline:** 2-3 days

---

## C4: Create RGPD-Compliant Database

### Task 4.1: Design Database Schema (Merise)
✅ **What to do:**
- Create MCD → MLD → MPD using Merise methodology
- Entities: `Email`, `User`, `ThreatLog`, `ModelVersion`
- Document RGPD-sensitive fields (email addresses, sender names)

📋 **Deliverable:** Merise diagrams (PDF/PNG) + `sql/schema.sql`

🔧 **Tools:** Draw.io or JMerise

⏱️ **Timeline:** 3-5 days

✔️ **Acceptance Criteria:**
- Correct Merise notation
- Primary/foreign keys and cardinalities shown
- Schema executes without errors in PostgreSQL

---

### Task 4.2: RGPD Compliance Documentation
✅ **What to do:**
- Create "Registre des traitements"
- Document: anonymization of sender addresses (replace with `[EMAIL]`), body text stored encrypted, retention policy (delete raw emails after 90 days, keep anonymized text + label)
- Reference your existing `anonymize_email()` function from the pipeline

📋 **Deliverable:** `docs/rgpd_compliance.md` + `registre_traitements.pdf`

⏱️ **Timeline:** 3-4 days

✔️ **Acceptance Criteria:**
- Register includes: purpose, legal basis, data categories, retention period
- Anonymization script provided and versioned on GitHub

---

## C5: Develop REST API for Data Access

### Task 5.1: Build FastAPI REST API
✅ **What to do:**
- Create FastAPI app with endpoints:
  - `GET /emails?label=phishing&language=fr&limit=100`
  - `GET /emails/{id}`
  - `GET /stats` (total samples, class balance, source distribution)
- Implement JWT authentication (API key for dataset access)
- Add rate limiting

📋 **Deliverable:** `api/main.py` + auto-generated OpenAPI spec at `/docs`

🔧 **Tools:** FastAPI, `python-jose`, `fastapi-limiter`

⏱️ **Timeline:** 5-7 days

✔️ **Acceptance Criteria:**
- API responds correctly to all endpoints
- Authentication blocks unauthorized requests (401)
- OpenAPI docs accessible and accurate

---

### Task 5.2: API Security (OWASP Top 10)
✅ **What to do:**
- Parameterized queries (prevent SQL injection)
- HTTPS (Cloud Run enforces TLS automatically)
- Rate limiting (100 req/hour per API key)
- CORS configured for dashboard origin only

📋 **Deliverable:** `docs/api_security_checklist.md`

⏱️ **Timeline:** 2-3 days

---

**BLOC 1 Total Timeline:** 6-8 weeks

---

# BLOC 2: AI Model Integration

**Evaluation:** E2 (Veille Case Study) + E3 (Project Demo)

**Project Context:** Benchmark existing AI services against Sicurre's approach, fine-tune CamemBERTv2 on your French phishing corpus, build the classification REST API (your LyScout pipeline, now packaged for Sicurre), monitor model performance with Grafana/W&B, and set up a full MLOps CI/CD pipeline with GitHub Actions + Cloud Run.

---

## C6: Organize Technical & Regulatory Monitoring (Veille)

### Task 6.1: Set Up Technical Monitoring
✅ **What to do:**
- Choose aggregation tool (Feedly + custom RSS)
- Identify 10+ sources:
  - CERT-FR alerts (French phishing IOCs — direct relevance to retraining)
  - HuggingFace blog (CamemBERT updates)
  - arXiv cs.CR (phishing detection papers)
  - ANSSI advisories
  - Trotta.io blog (competitor tracking)
  - GitHub trending (security/NLP repos)
- Schedule weekly 1-hour veille sessions
- Share summaries in `docs/veille/week-XX.md`

📋 **Deliverable:** 12 weekly veille summaries in GitHub repo

🔧 **Tools:** Feedly, RSS reader, Notion or Markdown

⏱️ **Timeline:** 1 hour/week × 12 weeks

✔️ **Acceptance Criteria:**
- 10+ sources documented with reliability justification
- Summaries link back to project relevance (e.g., "New CERT-FR IOC added to retraining queue")
- At least 2 summaries shared via GitHub Discussions (simulates stakeholder communication)

---

## C7: Benchmark AI Services

### Task 7.1: Formal Competitor & Service Benchmark
✅ **What to do:**
Research and compare these services for the benchmark report:

1. **InboxSentinel.ai** — English SaaS, no French model, generic
2. **Trotta.io** — Enterprise US, 4 LLM agents, $50K+/year, no French corpus
3. **Abnormal Security** — F500, behavioral AI, $100K+/year, not for SMB
4. **Google Safe Browsing API** — URL-only, no email content analysis, free
5. **Microsoft Defender API** — English-dominant, enterprise-only
6. **`cybersectony/phishing-email-detection-distilbert_v2.4.1`** (HuggingFace) — English DistilBERT, no French
7. **`camembert-base` raw (no fine-tuning)** — French but not phishing-specialized

Compare on: accuracy on French phishing, pricing, French language support, latency, RGPD compliance, SMB accessibility, setup complexity.

📋 **Deliverable:** `docs/service_benchmark.md` — table + recommendation

⏱️ **Timeline:** 5-7 days

✔️ **Acceptance Criteria:**
- 6+ services benchmarked
- Table includes all comparison dimensions
- Conclusion clearly states why Sicurre's CamemBERTv2 approach wins on French accuracy
- Services excluded are listed with reasons

---

## C8: Configure AI Service

### Task 8.1: Fine-Tune CamemBERTv2 on French Phishing Corpus
✅ **What to do:**
- Load `almanach/camembertv2-base` from HuggingFace
- Apply your existing tokenization and training pipeline (already built for LyScout — adapt for French corpus)
- Train for 3–5 epochs with early stopping
- Target: 95%+ F1 on French test set

📋 **Deliverable:** `notebooks/camembertv2_finetune.ipynb` + model in `models/Sicurre-phishing-fr/`

🔧 **Tools:** HuggingFace `transformers`, `torch`, Google Colab Pro (T4 GPU)

⏱️ **Timeline:** 7-10 days (including training time ~2-4 hours on T4)

✔️ **Acceptance Criteria:**
- 95%+ F1 on French phishing test set
- Training curves documented (loss/F1 over epochs)
- Model uploaded to HuggingFace Hub

---

### Task 8.2: Publish Model as Open-Source on HuggingFace Hub
✅ **What to do:**
- Upload fine-tuned model publicly: `Sicurre/camembertv2-phishing-fr`
- Write thorough Model Card:
  - Description and intended use (French email phishing detection)
  - Training data sources (CERT-FR, PhishTank, synthetic generation)
  - Evaluation metrics on French test set (F1, precision, recall)
  - Limitations (performs better on French than English phishing)
  - RGPD and ethical use statement

📋 **Deliverable:** Public HuggingFace model URL + Model Card

🔧 **Tools:** `huggingface_hub`, HuggingFace web interface

⏱️ **Timeline:** 1-2 days

✔️ **Acceptance Criteria:**
- Model publicly accessible by URL
- Model Card explains French phishing focus specifically
- Jury can visit URL during defence demo

> 💡 **Defence talking point:** *"The model is open-source — anyone can download and run it locally. What Sicurre charges for is the integration, the real-time inbox remediation, and the continuous retraining pipeline. This is the open-core model used by companies like Grafana, MongoDB, and Elastic. Transparency is also our biggest trust argument — unlike Trotta or Abnormal, you can audit exactly how we classify your email."*

---

### Task 8.3: Set Up Training Monitoring Dashboard
✅ **What to do:**
- Configure Weights & Biases (W&B) free tier
- Track: loss, F1, precision, recall per epoch
- Log model checkpoints
- Create public dashboard link (shareable with jury)

📋 **Deliverable:** W&B project link + screenshot

🔧 **Tools:** Weights & Biases

⏱️ **Timeline:** 2-3 days

---

## C9: Develop Classification API

### Task 9.1: Build FastAPI Model Serving Endpoint
✅ **What to do:**
- Wrap Sicurre model in REST API (extension of your existing LyScout pipeline):
  - `POST /classify` → Input: `{"subject": "...", "body": "...", "sender": "..."}` → Output: `{"label": "phishing", "confidence": 0.97, "signals": ["URSSAF impersonation", "suspicious URL", "DMARC fail"]}`
  - `POST /classify/batch` → batch of emails
- Integrate DMARC/SPF validation (already built in LyScout)
- ONNX quantized model for sub-200ms inference
- API key authentication

📋 **Deliverable:** `api/classifier.py` deployed on Cloud Run

🔧 **Tools:** FastAPI, `onnxruntime`, `checkdmarc`, Cloud Run

⏱️ **Timeline:** 5-7 days

✔️ **Acceptance Criteria:**
- API returns prediction + confidence + signal breakdown in <200ms
- DMARC validation integrated
- Authentication blocks unauthorized requests

---

### Task 9.2: Write Integration Tests
✅ **What to do:**
- Test all endpoints with `pytest` + `httpx`
- Cover your actual known test cases:
  - Real French URSSAF phishing → label=phishing
  - Real legitimate CAF email → label=legitimate
  - Email with DMARC fail → elevated phishing score
  - Empty body → graceful error (not 500)
- 80%+ code coverage

📋 **Deliverable:** `tests/test_classifier_api.py` + coverage report

🔧 **Tools:** `pytest`, `pytest-cov`, `httpx`

⏱️ **Timeline:** 3-4 days

---

## C10: Integrate API into Application

### Task 10.1: Build React Dashboard (Frontend)
✅ **What to do:**
- Create dashboard calling classification API:
  - Manual email input form → classification result with highlighted suspicious tokens
  - Confidence score bar
  - Signal breakdown (which features triggered: DMARC, URL, content)
  - "Was this correct?" feedback button (feeds retraining loop)
- Accessibility: keyboard navigation, ARIA labels, WCAG AA compliance

📋 **Deliverable:** `frontend/` React app

🔧 **Tools:** React, Tailwind CSS, `fetch` API

⏱️ **Timeline:** 5-7 days

✔️ **Acceptance Criteria:**
- Calls classification API correctly
- Displays confidence score + signal breakdown
- Keyboard navigation works (tested with WAVE browser extension)

---

## C11: Monitor Model Performance

### Task 11.1: Set Up Production Model Monitoring
✅ **What to do:**
- Prometheus + Grafana stack on Cloud Run
- Track:
  - Inference latency (p50, p95, p99)
  - Phishing detection rate (how many flagged per day)
  - Model drift indicator (rolling F1 on manually reviewed labels)
  - DMARC failure rate (separate from model confidence)
- Alert rule: "F1 drops below 90% → trigger retraining webhook"

📋 **Deliverable:** `monitoring/grafana_dashboard.json` + screenshot

🔧 **Tools:** Prometheus, Grafana, `prometheus-fastapi-instrumentator`

⏱️ **Timeline:** 5-7 days

---

## C12: Program Automated Model Tests

### Task 12.1: Write Model Unit Tests
✅ **What to do:**
- Test your actual pipeline components:
  - DistilBERT/CamemBERT tokenization correctness on French text with accents (é, è, ç)
  - DMARC validation output format
  - Score aggregation logic (hybrid voting)
  - Label normalization (0/1 consistency)
- Use `pytest` + mock for external calls

📋 **Deliverable:** `tests/test_model.py` + `tests/test_pipeline.py`

⏱️ **Timeline:** 3-4 days

✔️ **Acceptance Criteria:**
- 10+ test cases
- Tests complete in <30 seconds
- All pass on clean run

---

## C13: Create CI/CD Pipeline

### Task 13.1: GitHub Actions CI/CD
✅ **What to do:**
- `.github/workflows/ci.yml` triggers on push to `main`:
  1. Run `pytest` (all tests)
  2. Build Docker image
  3. Push to Google Artifact Registry
  4. Deploy to Cloud Run (staging)
  5. On manual approval → deploy to production
- DVC for dataset versioning (link dataset versions to model versions)

📋 **Deliverable:** `.github/workflows/ci.yml` + workflow run logs (screenshot)

🔧 **Tools:** GitHub Actions, Docker, Cloud Run, DVC

⏱️ **Timeline:** 5-7 days

✔️ **Acceptance Criteria:**
- Pipeline runs successfully on push
- Deployment blocked if tests fail
- DVC tracks dataset version used for each model

---

**BLOC 2 Total Timeline:** 8-10 weeks

---

# BLOC 3: Full Application Development

**Evaluation:** E4 (Project Demo + Report) + E5 (Monitoring Case Study)

**Project Context:** Design, develop, test, and deploy Sicurre as a complete SaaS application with Gmail API integration (Pub/Sub watch → classify → trash) and M365 Graph API support. The application includes a React dashboard showing threat logs, statistics, and user settings.

---

## C14: Analyze Application Requirements

### Task 14.1: Write User Stories
✅ **What to do:**
- Create 10+ user stories for your actual ICP (French auto-entrepreneur):
  ```
  As a French auto-entrepreneur,
  I want to connect my Gmail account with one click,
  So that phishing emails are automatically removed before I read them.

  As a French auto-entrepreneur,
  I want to see why an email was flagged as phishing,
  So that I can trust the system and recover false positives.

  As a French auto-entrepreneur,
  I want to restore a falsely flagged email from the dashboard,
  So that I never lose a legitimate email permanently.
  ```

📋 **Deliverable:** `docs/user_stories.md`

⏱️ **Timeline:** 2-3 days

✔️ **Acceptance Criteria:**
- 10+ user stories in correct format (role, goal, benefit)
- Acceptance criteria per story
- French user context reflected (not generic English personas)

---

### Task 14.2: Wireframes
✅ **What to do:**
- Design wireframes for:
  - Onboarding page (OAuth connect Gmail button)
  - Dashboard (threat log, statistics: emails scanned, phishing removed, accuracy)
  - Email detail page (why flagged, token highlights, DMARC/URL signals)
  - Settings page (auto-remove on/off, sensitivity threshold)
  - Restore/undo page

📋 **Deliverable:** `docs/wireframes.pdf` (Figma or Draw.io)

⏱️ **Timeline:** 3-5 days

---

### Task 14.3: Data Flow Diagram
✅ **What to do:**
- DFD showing Sicurre's complete flow:
  `Gmail/M365 → Pub/Sub/Graph webhook → Cloud Run Ingestion → Classifier API → Verdict → Remediation (trash) → PostgreSQL audit log → Dashboard`

📋 **Deliverable:** `docs/data_flow_diagram.png`

⏱️ **Timeline:** 1-2 days

---

## C15: Design Technical Architecture

### Task 15.1: Architecture Document
✅ **What to do:**
- Document Sicurre's microservices:
  1. `gmail-listener` — Cloud Run Function, Pub/Sub subscriber
  2. `phishing-api` — Cloud Run Service, FastAPI (classifier + DMARC + URL check)
  3. `remediator` — Cloud Run Function, executes Gmail trash action
  4. `dashboard` — Streamlit (POC) / React (prod), static hosting or Cloud Run
  5. `db` — Neon PostgreSQL (prod) / SQLite (dev) — email logs, user data, threat audit
- Include architecture diagram

📋 **Deliverable:** `docs/architecture.md` + diagram

⏱️ **Timeline:** 3-5 days

---

### Task 15.2: Proof of Concept
✅ **What to do:**
- You already have a working pipeline — package it as a formal PoC:
  - Gmail API OAuth → fetch email → hybrid classifier → verdict logged
  - Report on feasibility, latency measured, bottlenecks identified

📋 **Deliverable:** `poc/Sicurre_poc.py` + PoC report (1-2 pages)

⏱️ **Timeline:** 3-5 days (documentation of what you've already built)

---

## C16: Coordinate Agile Project

### Task 16.1: Agile Board
✅ **What to do:**
- GitHub Projects Kanban board
- 3 sprints × 2 weeks (Sprint 1: Data pipeline, Sprint 2: Model + API, Sprint 3: App + deployment)
- Sprint retrospectives documented

📋 **Deliverable:** GitHub Projects board screenshot + 3 retrospective notes

⏱️ **Timeline:** Setup 1 day, maintenance throughout

---

## C17: Develop Application Components

### Task 17.1: Gmail Integration Service
✅ **What to do:**
- OAuth 2.0 flow (user grants `gmail.modify` scope)
- `gmail.users.watch()` → subscribe to Pub/Sub topic
- Cloud Run Function receives Pub/Sub push notification (1-2s latency)
- Fetches full email via `gmail.users.messages.get()`
- Passes to classifier

📋 **Deliverable:** `services/gmail_listener/main.py` + Cloud Run deployment

🔧 **Tools:** Gmail API, Google Cloud Pub/Sub, Cloud Run

⏱️ **Timeline:** 7-10 days

✔️ **Acceptance Criteria:**
- Real email detected and classified within 2-5 seconds of arrival
- Watch renewal job scheduled (every 6 days — Gmail watch expires at 7)

---

### Task 17.2: Remediation Service
✅ **What to do:**
- On phishing verdict (confidence >0.85): call `gmail.users.messages.trash()`
- Log to PostgreSQL: `(user_id, message_id, verdict, confidence, timestamp, signals)`
- Emit Prometheus counter: `Sicurre_phishing_removed_total`
- Implement "undo" endpoint: restore from trash within 7 days

📋 **Deliverable:** `services/remediator/main.py`

⏱️ **Timeline:** 3-5 days

---

### Task 17.3: Dashboard (React)
✅ **What to do:**
- Threat log: paginated list of detected phishing with date, sender (anonymized), confidence, signals
- Stats panel: total scanned, phishing removed today/week/month, model accuracy
- Settings: auto-remove toggle, confidence threshold slider
- Undo button: restore email from trash
- Language: French UI by default (your target user is French-speaking)

📋 **Deliverable:** `frontend/` deployed on Cloud Run (or static hosting)

🔧 **Tools:** React, Tailwind CSS, Recharts (for stats charts)

⏱️ **Timeline:** 7-10 days

---

### Task 17.4: Authentication (Google OAuth)
✅ **What to do:**
- "Sign in with Google" flow
- Store user_id + Gmail token in PostgreSQL (encrypted)
- JWT session tokens for dashboard API calls
- Revocation endpoint (user can disconnect Gmail)

📋 **Deliverable:** `auth/` module

⏱️ **Timeline:** 5-7 days

---

### Task 17.5: Tests + Security Audit
✅ **What to do:**
- Unit tests: each service
- Integration test: full end-to-end (email arrives → classified → trashed → logged → visible in dashboard)
- OWASP Top 10 checklist: SQL injection (parameterized), XSS (sanitize), CSRF tokens, secure headers

📋 **Deliverable:** `tests/` directory + `docs/security_audit.md`

⏱️ **Timeline:** 5-7 days

---

## C18: Automate Testing (CI)

### Task 18.1: Tests in CI Pipeline
✅ **What to do:**
- GitHub Actions runs `pytest` on every commit to every branch
- Deployment blocked if any test fails

📋 **Deliverable:** Updated `ci.yml` + failed-test screenshot (proof)

⏱️ **Timeline:** 1-2 days

---

## C19: Continuous Delivery

### Task 19.1: Automated Production Deployment
✅ **What to do:**
- On merge to `main` → build Docker → push to Artifact Registry → deploy to Cloud Run production
- Rollback: `gcloud run services update-traffic --to-revisions=PREVIOUS=100`
- Document rollback procedure

📋 **Deliverable:** CD config + deployment logs + rollback test

⏱️ **Timeline:** 3-5 days

---

## C20: Monitor Application

### Task 20.1: Application Monitoring Stack
✅ **What to do:**
- Sentry: error tracking (catches exceptions in classifier, Gmail API errors, DB failures)
- Grafana dashboard:
  - API request rate + error rate
  - Inference latency p95
  - Phishing emails removed per hour
  - Gmail watch expiry countdown (alert at 24h before expiry)
- UptimeRobot: public uptime monitoring (share URL with jury)

📋 **Deliverable:** Sentry project + Grafana dashboard screenshot + UptimeRobot badge

⏱️ **Timeline:** 3-5 days

---

## C21: Debug and Resolve Incident

### Task 21.1: Simulate and Resolve a Real Bug
✅ **What to do:**
- Introduce a realistic bug (e.g., Gmail watch expires silently — emails stop being checked but user gets no alert)
- Document error in Sentry / monitoring log
- Fix bug (add watch renewal job + expiry alert)
- Write post-mortem:
  - What happened: watch expired after 7 days, no renewal job
  - Root cause: Cloud Scheduler not configured
  - Fix: added daily Cloud Scheduler job calling `gmail.users.watch()` renewal
  - Prevention: added Grafana alert for "watch age > 6 days"

📋 **Deliverable:** `docs/incident_postmortem.md` + fixed code commit on GitHub

⏱️ **Timeline:** 2-3 days

✔️ **Acceptance Criteria:**
- Realistic bug scenario (not trivial)
- 5 Whys root cause analysis
- Prevention measure implemented and documented

---

**BLOC 3 Total Timeline:** 10-12 weeks

---

# Final Deliverables Checklist

## For E1 (Bloc 1 — Data Pipeline)
- [ ] Professional report (PDF, 20-30 pages) — context, technical specs, results
- [ ] GitHub repo: `scripts/`, `sql/`, `api/`, `docs/`
- [ ] RGPD documentation + registre des traitements
- [ ] Merise diagrams (MCD, MLD, MPD)
- [ ] REST API live (public URL with `/docs` OpenAPI page)
- [ ] French phishing dataset: 6,000+ samples published
- [ ] Oral defence slides

## For E2 (Bloc 2 — Veille & Benchmark)
- [ ] 12 weekly veille summaries (`docs/veille/`)
- [ ] Formal competitor benchmark report (7 services compared)
- [ ] Service configuration documentation

## For E3 (Bloc 2 — Model Integration)
- [ ] Professional report (PDF)
- [ ] Live demo: type French email → get phishing/legitimate + confidence + signals
- [ ] HuggingFace model public URL (`Sicurre/camembertv2-phishing-fr`)
- [ ] W&B training dashboard (public link)
- [ ] GitHub Actions CI/CD workflow logs
- [ ] Test coverage report (80%+)
- [ ] Grafana model monitoring dashboard

## For E4 (Bloc 3 — Application)
- [ ] Professional report (PDF)
- [ ] Live demo: real Gmail email arrives → flagged → auto-removed in <5s
- [ ] Architecture diagram (services + data flows)
- [ ] User stories (10+) + wireframes
- [ ] GitHub Projects Kanban board (3 sprint history)
- [ ] OWASP security audit checklist
- [ ] Accessibility report (WAVE browser extension results)

## For E5 (Bloc 3 — Monitoring & Incident)
- [ ] Monitoring documentation (Sentry + Grafana setup)
- [ ] Incident post-mortem (Gmail watch expiry bug)
- [ ] Sentry error log screenshot
- [ ] Prevention measure code commit

---

# Overall Project Timeline

| Phase | Duration | Key Milestones |
|-------|----------|----------------|
| **Phase 1: Data Pipeline (Bloc 1)** | 6-8 weeks | French phishing corpus live, REST API deployed |
| **Phase 2: Model Training (Bloc 2)** | 8-10 weeks | CamemBERTv2 fine-tuned, 95%+ F1, public on HuggingFace |
| **Phase 3: Application Build (Bloc 3)** | 10-12 weeks | Gmail integration live, production on Cloud Run |
| **Phase 4: Defence Prep** | 2-3 weeks | Reports written, demo rehearsed |
| **Total** | **26-33 weeks (6-8 months)** | Ready for defence |

---

**Document Version:** 2.0 (Updated: February 28, 2026)
**Author:** Adebayo Michael
**Product:** Sicurre — French-Native Real-Time Phishing Detection
**Programme:** Titre Développeur en Intelligence Artificielle (Dev IA)
**Status:** Active development — building toward defence and product launch

# ADR-0002: CamemBERTv2 as French base model

**Date:** 2026-02-28  
**Status:** Accepted  

## Context
Most phishing detectors are English-centric. Sicurre needs strong French linguistic performance for URSSAF/DGFiP/CAF impersonation patterns.

## Decision
Use CamemBERTv2 (French-native transformer) as base model and fine-tune on curated French phishing corpus.

## Alternatives
- DistilBERT phishing models: English-trained, poor French coverage
- mBERT/XLM-R: multilingual but typically weaker than French-native for FR nuance

## Consequences
- Better French accuracy
- Need to build/curate French corpus + RGPD constraints

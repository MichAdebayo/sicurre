# ADR-0002: CamemBERTav2 as French base model for 3-class classification

**Date:** 2026-02-28  
**Updated:** 2026-03-03  
**Status:** Accepted (supersedes original CamemBERTv2 decision)  

## Context

Most phishing detectors are English-centric and binary (phishing vs legitimate). Sicurre needs:

1. **Strong French linguistic performance** for URSSAF/DGFiP/CAF impersonation patterns, formal "vous" register, accent-based homographs, and French administrative vocabulary.
2. **Three-class classification** — phishing, spam, and legitimate — because the French training corpus contains distinct spam data (Kaggle Multilingual FR, French SpamHam) that is semantically different from targeted phishing. Collapsing spam into phishing would reduce model precision on true phishing detection.

## Decision

Use **CamemBERTav2** (`almanach/camembertav2-base`) as the base model, fine-tuned with `num_labels=3` for three-class sequence classification:

| Label | ID | Description |
|-------|----|-------------|
| phishing | 0 | Targeted phishing emails (credential harvesting, spear-phishing, admin impersonation) |
| spam | 1 | Unsolicited bulk/commercial messages (not targeted attacks) |
| legitimate | 2 | Normal, expected emails |

```python
from transformers import AutoModelForSequenceClassification, AutoTokenizer

model = AutoModelForSequenceClassification.from_pretrained(
    "almanach/camembertav2-base",
    num_labels=3,  # phishing=0, spam=1, legitimate=2
)
tokenizer = AutoTokenizer.from_pretrained("almanach/camembertav2-base")
```

The model is exported to **ONNX Runtime with INT8 quantization** for production inference (same as before — DeBERTaV2 exports via `optimum`).

## Why CamemBERTav2 over CamemBERTv2

Both models are from the same team (ALMAnaCH/Inria), same MIT license, same 275B-token French training corpus, same tokenizer (WordPiece 32,768 tokens, 1024 context window). The key difference is architecture:

| | CamemBERTv2 (previous) | **CamemBERTav2 (new)** |
|--|------------------------|------------------------|
| Hub ID | `almanach/camembertv2-base` | **`almanach/camembertav2-base`** |
| Architecture | RoBERTa | **DeBERTaV3** |
| Training objective | MLM (learns from 40% masked tokens) | **RTD — Replaced Token Detection (learns from ALL tokens)** |
| Attention mechanism | Standard self-attention | **Disentangled attention (separate content + position)** |
| Parameters | 110M | 110M |
| XNLI (text classification) | 81.75 | **84.82 (+3.07)** |
| CLS (text classification) | 80.98 | **83.04 (+2.06)** |
| PAWS-X (paraphrase) | 61.35 | **64.29 (+2.94)** |
| NER (FTB) | 91.99 | **93.40 (+1.41)** |
| FQuAD (QA) | 87.46 | **89.53 (+2.07)** |
| Medical NER | 72.77 | **73.98 (+1.21)** |

**CamemBERTav2 outperforms CamemBERTv2 on every benchmark**, with the largest gains (+2–3 points) on **text classification tasks** — which is Sicurre's exact use case.

The DeBERTaV3 RTD objective trains on every token position (not just the 40% that are masked), giving significantly better sample efficiency during fine-tuning. This is critical given Sicurre's limited French training corpus (~7K samples).

## Alternatives considered

| Model | Architecture | French text classification | Why not |
|-------|-------------|---------------------------|---------|
| **CamemBERTv2** | RoBERTa (MLM) | 81.75 XNLI | Superseded by CamemBERTav2 from same team; 3 points lower on classification |
| **CamemBERT v1** | RoBERTa (MLM, 32B tokens) | 81.95 XNLI | Older, smaller training data (32B vs 275B tokens), temporal drift |
| **mBERT** | BERT multilingual | ~88-90% est. | 180M params, diluted across 104 languages; weaker on FR nuance |
| **XLM-RoBERTa** | RoBERTa multilingual | ~90-92% est. | 270M params, 2.5x larger/slower; multilingual overhead |
| **DistilBERT (EN)** | Distilled BERT | ~82-85% est. | English-only; fails on French formal register and admin vocabulary |
| **DistilCamemBERT** | Distilled CamemBERT | ~97% of CamemBERT v1 | No v2 distilled variant yet; would sacrifice accuracy on small corpus |

## Why 3-class over binary

| Approach | Pros | Cons |
|----------|------|------|
| Binary (phishing vs legitimate) | Simpler | Spam-as-phishing inflates false positives; users lose trust when bulk marketing is flagged as "phishing" |
| **3-class (phishing, spam, legitimate)** | Distinct remediation actions per class; higher precision on true phishing; better user trust | Slightly more training data needed per class |

Remediation differs by class:
- **Phishing → Trash** (automatic, high confidence)
- **Spam → Label/archive** (softer action, user-configurable)
- **Legitimate → No action**

## Consequences

- Better French text classification accuracy (+3 points over CamemBERTv2)
- Better fine-tuning sample efficiency (RTD uses all tokens)
- Need to relabel training data with 3-class schema (phishing=0, spam=1, legitimate=2)
- DB `verdict` column and API contract must support 3 values
- ONNX export unchanged — `optimum` supports DeBERTaV2/V3
- Same MIT license, same team — no licensing risk

## References

- Paper: [CamemBERT 2.0: A Smarter French Language Model Aged to Perfection](https://arxiv.org/abs/2411.08868) (Antoun et al., 2024)
- HuggingFace: [almanach/camembertav2-base](https://huggingface.co/almanach/camembertav2-base)
- Benchmarks: Table 2 in the paper (all evaluation datasets)

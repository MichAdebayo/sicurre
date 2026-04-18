from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

ROOT_DIR = Path(__file__).resolve().parents[4]
SRC_ROOT = ROOT_DIR / "src"

if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT_DIR / ".env", override=True)

from core.config import get_settings
from data_platform.services.shared.adaptation import (
    ARCHETYPES,
    FrenchCulturalAdaptationService,
)
from data_platform.services.certfr.generated_drafts import CertFRGeneratedDraftService
from data_platform.services.common_crawl.signal_synthetic import (
    CommonCrawlSignalSyntheticService,
)
from data_platform.services.shared.llm_generation_feasibility import (
    LLMGenerationFeasibilityService,
    OpenAICompatibleInferenceClient,
    ProviderConfig,
    get_llm_generation_feasibility_settings,
)
from data_platform.services.shared.structured_review_artifact import (
    StructuredReviewArtifactService,
)
from db.models import DataNormalizedMessage, DataRawRecord, DataSourceSystem


DEFAULT_CERTFR_INPUT = (
    ROOT_DIR
    / "tasks/reviews/2026-04-10-specialized-no-write/certfr-synthesis-inputs.json"
)
DEFAULT_COMMON_CRAWL_INPUT = (
    ROOT_DIR
    / "tasks/reviews/2026-04-10-specialized-no-write/common-crawl-live-full-export.json"
)


async def _load_english_phishing_seeds(source_names: list[str]) -> list[dict[str, Any]]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    rows: list[dict[str, Any]] = []

    async with session_factory() as session:
        query = (
            select(DataRawRecord.id, DataRawRecord.raw_content, DataSourceSystem.name)
            .join(
                DataSourceSystem, DataSourceSystem.id == DataRawRecord.source_system_id
            )
            .where(DataSourceSystem.name.in_(source_names))
        )
        result = await session.execute(query)
        for raw_record_id, raw_content, source_name in result.all():
            payload = json.loads(str(raw_content))
            raw_label = str(payload.get("label") or "").strip().lower()
            if raw_label not in {"1", "phishing"}:
                continue
            text = str(payload.get("text") or "").strip()
            if not text:
                continue
            rows.append(
                {
                    "raw_record_id": str(raw_record_id),
                    "text": text,
                    "source": str(source_name),
                }
            )

    await engine.dispose()
    return rows


async def _load_normalized_anchors(label: str) -> list[dict[str, Any]]:
    settings = get_settings()
    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        result = await session.execute(
            select(
                DataNormalizedMessage.id,
                DataNormalizedMessage.normalized_text,
                DataNormalizedMessage.current_label,
            ).where(DataNormalizedMessage.current_label == label)
        )
        rows = [
            {
                "id": str(message_id),
                "normalized_text": text,
                "current_label": current_label,
            }
            for message_id, text, current_label in result.all()
        ]

    await engine.dispose()
    return rows


def _pick_diverse_adapted_cases(
    matched_rows: list[dict[str, Any]],
    *,
    max_cases: int,
) -> list[dict[str, Any]]:
    by_archetype: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in matched_rows:
        for archetype in row.get("archetypes", []):
            by_archetype[str(archetype)].append(row)

    chosen: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for archetype in sorted(by_archetype):
        for row in by_archetype[archetype]:
            raw_record_id = str(row.get("raw_record_id") or "")
            if raw_record_id in seen_ids:
                continue
            chosen.append({**row, "selected_archetype": archetype})
            seen_ids.add(raw_record_id)
            break
        if len(chosen) >= max_cases:
            return chosen[:max_cases]

    for row in matched_rows:
        raw_record_id = str(row.get("raw_record_id") or "")
        if raw_record_id in seen_ids:
            continue
        chosen.append({**row, "selected_archetype": row.get("archetypes", [""])[0]})
        seen_ids.add(raw_record_id)
        if len(chosen) >= max_cases:
            break
    return chosen[:max_cases]


def _pick_synthetic_cases(
    payload: dict[str, Any], *, source_kind: str, max_cases: int
) -> list[dict[str, Any]]:
    if source_kind == "certfr":
        return list(payload.get("scenarios") or [])[:max_cases]

    candidates = [
        candidate
        for candidate in payload.get("candidates", [])
        if str(candidate.get("rule_key") or "") == "phishing_lure_candidate"
        and str(candidate.get("target_label") or "") == "phishing"
    ]
    return candidates[:max_cases]


def _resolve_fr_entity(archetype: str) -> str:
    return str(ARCHETYPES.get(archetype, {}).get("fr_entity") or archetype)


def _resolve_providers(args: argparse.Namespace) -> list[ProviderConfig]:
    settings = get_llm_generation_feasibility_settings()
    provider_names = [
        name.strip().lower() for name in args.providers.split(",") if name.strip()
    ]
    providers: list[ProviderConfig] = []

    for name in provider_names:
        if name == "cerebras":
            api_key = settings.cerebras_api_key
            model = args.cerebras_model or settings.cerebras_model
            base_url = settings.cerebras_base_url
        elif name == "groq":
            api_key = settings.groq_api_key
            model = args.groq_model or settings.groq_model
            base_url = settings.groq_base_url
        elif name == "grok":
            api_key = settings.xai_api_key
            model = args.grok_model or settings.xai_model
            base_url = settings.xai_base_url
        else:
            raise ValueError(f"Unsupported provider: {name}")

        if not args.dry_run and (not api_key or not model):
            raise ValueError(
                f"Provider {name} requires an API key and model via env or CLI."
            )
        providers.append(
            ProviderConfig(
                name=name,
                api_key=api_key or "dry-run",
                base_url=base_url,
                model=model or f"{name}-model-not-configured",
            )
        )
    return providers


async def _run_provider_completion(
    provider: ProviderConfig,
    *,
    system_prompt: str,
    user_prompt: str,
    dry_run: bool,
) -> dict[str, Any]:
    if dry_run:
        return {
            "provider": provider.name,
            "model": provider.model,
            "status": "dry_run",
            "text": None,
        }

    client = OpenAICompatibleInferenceClient(
        provider,
        timeout_seconds=get_llm_generation_feasibility_settings().inference_timeout_seconds,
    )
    try:
        text = await client.complete(
            system_prompt=system_prompt, user_prompt=user_prompt
        )
        return {
            "provider": provider.name,
            "model": provider.model,
            "status": "completed",
            "text": text,
        }
    except Exception as exc:  # pragma: no cover - network/provider path
        return {
            "provider": provider.name,
            "model": provider.model,
            "status": "failed",
            "error": str(exc),
            "text": None,
        }


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# LLM Feasibility Comparison",
        "",
        f"- Generated at: {payload.get('generated_at')}",
        f"- Providers: {', '.join(payload.get('providers', []))}",
        f"- Adapted prompt mode: {payload.get('adapted_prompt_mode')}",
        f"- Prompt context mode: {payload.get('prompt_context_mode')}",
        f"- Adapted cases: {len(payload.get('adapted_cases', []))}",
        f"- Synthetic cases: {len(payload.get('synthetic_cases', []))}",
        "",
    ]

    for section_name in ("adapted_cases", "synthetic_cases"):
        title = (
            "Adapted Cases" if section_name == "adapted_cases" else "Synthetic Cases"
        )
        lines.extend([f"## {title}", ""])
        for case in payload.get(section_name, []):
            lines.extend(
                [
                    f"### {case['case_id']}",
                    "",
                    f"- Reference count: {len(case.get('references', []))}",
                    f"- Template pipeline kind: {case.get('template_kind')}",
                    "",
                    "#### Template Output",
                    "",
                    case.get("template_text") or "(missing)",
                    "",
                ]
            )
            for provider_output in case.get("provider_outputs", []):
                lines.extend(
                    [
                        f"#### {provider_output['provider']} ({provider_output['status']})",
                        "",
                        provider_output.get("text")
                        or provider_output.get("error")
                        or "(no output)",
                        "",
                    ]
                )
        lines.append("")
    return "\n".join(lines)


async def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Run a small side-by-side feasibility comparison between the current "
            "deterministic generation pipelines and model-backed Cerebras/Grok rewrites."
        )
    )
    parser.add_argument("--providers", type=str, default="cerebras,grok")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cerebras-model", type=str, default=None)
    parser.add_argument("--groq-model", type=str, default=None)
    parser.add_argument("--grok-model", type=str, default=None)
    parser.add_argument("--adapted-sources", type=str, default="zefang_phishing")
    parser.add_argument("--adapted-cases", type=int, default=4)
    parser.add_argument(
        "--adapted-prompt-mode",
        choices=["translate_localize", "context_brief"],
        default="translate_localize",
    )
    parser.add_argument(
        "--prompt-context-mode",
        choices=["sanitized", "explicit_phishing"],
        default="sanitized",
    )
    parser.add_argument(
        "--synthetic-source", choices=["certfr", "common-crawl"], default="certfr"
    )
    parser.add_argument("--synthetic-cases", type=int, default=4)
    parser.add_argument("--reference-top-k", type=int, default=3)
    parser.add_argument(
        "--retrieval-backend",
        choices=["auto", "sentence-transformer", "tfidf"],
        default="auto",
    )
    parser.add_argument("--embedding-model", type=str, default=None)
    parser.add_argument("--normalized-label", type=str, default="phishing")
    parser.add_argument("--certfr-input", type=Path, default=DEFAULT_CERTFR_INPUT)
    parser.add_argument(
        "--common-crawl-input", type=Path, default=DEFAULT_COMMON_CRAWL_INPUT
    )
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-md", type=Path, required=True)
    args = parser.parse_args()

    embedding_model_name = (
        args.embedding_model
        or get_llm_generation_feasibility_settings().embedding_model_name
    )
    providers = _resolve_providers(args)
    anchor_rows = await _load_normalized_anchors(args.normalized_label)

    source_names = [
        name.strip() for name in args.adapted_sources.split(",") if name.strip()
    ]
    english_rows = await _load_english_phishing_seeds(source_names)
    adaptation_service = FrenchCulturalAdaptationService(seed=42)
    matched_df = adaptation_service.attach_archetype_matches(pd.DataFrame(english_rows))
    matched_rows = matched_df.to_dict(orient="records")
    adapted_cases = _pick_diverse_adapted_cases(
        matched_rows, max_cases=args.adapted_cases
    )

    synthetic_payload = StructuredReviewArtifactService.read_json(
        args.certfr_input
        if args.synthetic_source == "certfr"
        else args.common_crawl_input
    )
    synthetic_cases = _pick_synthetic_cases(
        synthetic_payload,
        source_kind=args.synthetic_source,
        max_cases=args.synthetic_cases,
    )

    adapted_outputs: list[dict[str, Any]] = []
    for case in adapted_cases:
        archetype = str(case.get("selected_archetype") or "")
        template_rows = adaptation_service.generate_for_archetype(
            pd.DataFrame([case]),
            archetype,
            adaptation_service.template_map[archetype],
            target_count=1,
        )
        template_text = str(template_rows[0]["text"])
        references = LLMGenerationFeasibilityService.retrieve_reference_texts(
            retrieval_backend=args.retrieval_backend,
            query_text=str(case.get("text") or ""),
            anchor_rows=anchor_rows,
            embedding_model_name=embedding_model_name,
            top_k=args.reference_top_k,
        )
        references, retrieval_backend_used = references
        if args.adapted_prompt_mode == "context_brief":
            system_prompt, user_prompt = (
                LLMGenerationFeasibilityService.build_adapted_context_brief_prompts(
                    seed_text=str(case.get("text") or ""),
                    archetype=archetype,
                    fr_entity=_resolve_fr_entity(archetype),
                    references=references,
                    prompt_context_mode=args.prompt_context_mode,
                )
            )
        else:
            system_prompt, user_prompt = (
                LLMGenerationFeasibilityService.build_adapted_prompts(
                    seed_text=str(case.get("text") or ""),
                    archetype=archetype,
                    fr_entity=_resolve_fr_entity(archetype),
                    references=references,
                    prompt_context_mode=args.prompt_context_mode,
                )
            )
        provider_outputs = [
            await _run_provider_completion(
                provider,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                dry_run=args.dry_run,
            )
            for provider in providers
        ]
        adapted_outputs.append(
            {
                "case_id": f"adapted:{archetype}:{case.get('raw_record_id')}",
                "template_kind": "faker_template_adapted",
                "template_text": template_text,
                "seed_text": str(case.get("text") or ""),
                "adapted_prompt_mode": args.adapted_prompt_mode,
                "prompt_context_mode": args.prompt_context_mode,
                "references": references,
                "retrieval_backend_used": retrieval_backend_used,
                "provider_outputs": provider_outputs,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )

    synthetic_outputs: list[dict[str, Any]] = []
    for case in synthetic_cases:
        if args.synthetic_source == "certfr":
            draft = CertFRGeneratedDraftService.build_drafts({"scenarios": [case]})[
                "drafts"
            ][0]
            template_text = str(draft.get("full_text") or "")
            references = LLMGenerationFeasibilityService.retrieve_reference_texts(
                retrieval_backend=args.retrieval_backend,
                query_text=str(case.get("prompt_brief") or ""),
                anchor_rows=anchor_rows,
                embedding_model_name=embedding_model_name,
                top_k=args.reference_top_k,
            )
            references, retrieval_backend_used = references
            system_prompt, user_prompt = (
                LLMGenerationFeasibilityService.build_certfr_synthetic_prompts(
                    scenario=case,
                    references=references,
                    prompt_context_mode=args.prompt_context_mode,
                )
            )
            case_id = f"synthetic:certfr:{case.get('scenario_id')}"
            template_kind = "deterministic_signal_synthetic"
        else:
            draft = CommonCrawlSignalSyntheticService.build_drafts(
                {"candidates": [case]},
                variants_per_seed=1,
            )["drafts"][0]
            template_text = str(draft.get("normalized_text") or "")
            references = LLMGenerationFeasibilityService.retrieve_reference_texts(
                retrieval_backend=args.retrieval_backend,
                query_text=str(case.get("normalized_text") or ""),
                anchor_rows=anchor_rows,
                embedding_model_name=embedding_model_name,
                top_k=args.reference_top_k,
            )
            references, retrieval_backend_used = references
            system_prompt, user_prompt = (
                LLMGenerationFeasibilityService.build_common_crawl_synthetic_prompts(
                    seed_text=str(case.get("normalized_text") or ""),
                    references=references,
                    prompt_context_mode=args.prompt_context_mode,
                )
            )
            case_id = f"synthetic:common-crawl:{case.get('raw_record_id')}"
            template_kind = "deterministic_signal_rewrite"

        provider_outputs = [
            await _run_provider_completion(
                provider,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                dry_run=args.dry_run,
            )
            for provider in providers
        ]
        synthetic_outputs.append(
            {
                "case_id": case_id,
                "template_kind": template_kind,
                "template_text": template_text,
                "references": references,
                "retrieval_backend_used": retrieval_backend_used,
                "provider_outputs": provider_outputs,
                "system_prompt": system_prompt,
                "user_prompt": user_prompt,
            }
        )

    payload = {
        "mode": "llm_generation_feasibility_comparison",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "providers": [provider.name for provider in providers],
        "adapted_prompt_mode": args.adapted_prompt_mode,
        "prompt_context_mode": args.prompt_context_mode,
        "adapted_cases": adapted_outputs,
        "synthetic_source": args.synthetic_source,
        "synthetic_cases": synthetic_outputs,
        "embedding_model_name": embedding_model_name,
        "retrieval_backend": args.retrieval_backend,
        "normalized_label": args.normalized_label,
        "dry_run": args.dry_run,
    }
    StructuredReviewArtifactService.write_json(args.output_json, payload)
    args.output_md.parent.mkdir(parents=True, exist_ok=True)
    args.output_md.write_text(_render_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())

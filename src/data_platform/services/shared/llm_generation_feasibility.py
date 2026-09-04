from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT_DIR = Path(__file__).resolve().parents[3]
ENV_FILE = ROOT_DIR / ".env"


class LLMGenerationFeasibilitySettings(BaseSettings):
    groq_api_key: str | None = Field(default=None, validation_alias="GROQ_API_KEY")
    groq_base_url: str = Field(
        default="https://api.groq.com/openai/v1",
        validation_alias="GROQ_BASE_URL",
    )
    groq_model: str | None = Field(default=None, validation_alias="GROQ_MODEL")
    cerebras_api_key: str | None = Field(
        default=None, validation_alias="CEREBRAS_API_KEY"
    )
    cerebras_base_url: str = Field(
        default="https://api.cerebras.ai/v1",
        validation_alias="CEREBRAS_BASE_URL",
    )
    cerebras_model: str | None = Field(default=None, validation_alias="CEREBRAS_MODEL")
    xai_api_key: str | None = Field(default=None, validation_alias="XAI_API_KEY")
    xai_base_url: str = Field(
        default="https://api.x.ai/v1",
        validation_alias="XAI_BASE_URL",
    )
    xai_model: str | None = Field(default=None, validation_alias="XAI_MODEL")
    embedding_model_name: str = Field(
        default="paraphrase-multilingual-MiniLM-L12-v2",
        validation_alias="EMBEDDING_MODEL_NAME",
    )
    inference_timeout_seconds: float = Field(
        default=45.0, validation_alias="INFERENCE_TIMEOUT_SECONDS"
    )

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_llm_generation_feasibility_settings() -> LLMGenerationFeasibilitySettings:
    return LLMGenerationFeasibilitySettings()


@dataclass(frozen=True, slots=True)
class ProviderConfig:
    name: str
    api_key: str
    base_url: str
    model: str


class OpenAICompatibleInferenceClient:
    def __init__(
        self, config: ProviderConfig, *, timeout_seconds: float = 45.0
    ) -> None:
        self.config = config
        self.timeout_seconds = timeout_seconds

    async def complete(self, *, system_prompt: str, user_prompt: str) -> str:
        payload = {
            "model": self.config.model,
            "temperature": 0.3,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.config.base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()

        return self._extract_content(response.json())

    @staticmethod
    def _extract_content(payload: dict[str, Any]) -> str:
        choices = payload.get("choices") or []
        if not choices:
            raise ValueError("Provider response did not contain choices.")
        message = choices[0].get("message") or {}
        content = message.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts = [
                part.get("text", "") for part in content if isinstance(part, dict)
            ]
            merged = "\n".join(part.strip() for part in text_parts if part.strip())
            if merged:
                return merged
        raise ValueError("Provider response did not contain string content.")


class LLMGenerationFeasibilityService:
    ADAPTED_ARCHETYPE_CONSTRAINTS: dict[str, dict[str, tuple[str, ...]]] = {
        "ameli_sante": {
            "must_include": (
                "Frame the message as an Ameli or Assurance Maladie reimbursement or dossier verification flow.",
                "Ask the reader to confirm identity or update banking details through a link.",
                "Keep a reimbursement, dossier, or account-treatment consequence if the action is ignored.",
            ),
            "avoid": (
                "Do not turn it into a medicine promotion or pharmacy advertisement.",
                "Do not mention product catalogs or commercial health offers.",
            ),
        },
        "caf_allocation": {
            "must_include": (
                "Frame the message as a CAF declaration, allocation review, or benefit-suspension issue.",
                "Require the reader to complete a declaration or verify beneficiary information through a link.",
                "Mention suspension, interruption, or delay of allocations if no action is taken.",
            ),
            "avoid": (
                "Do not turn it into a generic account-security alert.",
                "Do not ask the reader to review an attachment or generic security document.",
            ),
        },
        "dgfip_tax": {
            "must_include": (
                "Frame the message as a DGFiP tax regularization, declaration anomaly, or payment-due notice.",
                "Ask the reader to regularize the file or access the tax portal through a link.",
                "Mention tax penalties, overdue status, or dossier treatment if ignored.",
            ),
            "avoid": (
                "Do not turn it into a bank-security or attachment-review message.",
                "Do not mention general banking monitoring or card security.",
            ),
        },
        "banque_securite": {
            "must_include": (
                "Frame the message as a French bank account-security or 3D Secure verification issue.",
                "Ask the reader to confirm identity or update the security device through a link.",
                "Mention payment refusal, account restriction, or transaction blocking if ignored.",
            ),
            "avoid": (
                "Do not ask the reader to open an attachment or security document.",
                "Do not mention foreign transfer partnerships, confidential remittances, or lottery-style scams.",
            ),
        },
        "franceconnect_id": {
            "must_include": (
                "Frame the message as a FranceConnect or identity-verification access issue.",
                "Ask the reader to confirm credentials or re-verify identity through a link.",
                "Mention access restriction or login interruption if ignored.",
            ),
            "avoid": (
                "Do not turn it into a generic invoice or parcel message.",
                "Do not mention unrelated bank-card updates.",
            ),
        },
        "facture_paiement": {
            "must_include": (
                "Frame the message as an EDF, telecom, or subscription invoice-payment regularization issue.",
                "Ask the reader to settle or confirm payment details through a link.",
                "Mention service interruption, penalties, or overdue treatment if ignored.",
            ),
            "avoid": (
                "Do not reduce it to a vague identity-check message.",
                "Do not ask the reader to inspect an attachment or security report.",
            ),
        },
        "laposte_colis": {
            "must_include": (
                "Frame the message as a parcel-delivery, customs-fee, or tracking-resolution issue.",
                "Ask the reader to pay a fee, confirm delivery details, or unlock shipment handling through a link.",
                "Mention delivery delay, return to sender, or blocked shipment if ignored.",
            ),
            "avoid": (
                "Do not turn it into a generic account-security notice.",
                "Do not mention bank statements or tax dossiers.",
            ),
        },
        "urssaf_cotisation": {
            "must_include": (
                "Frame the message as a URSSAF cotisation or employer-contribution regularization issue.",
                "Ask the reader to regularize the file or confirm contribution details through a link.",
                "Mention penalties, file suspension, or delayed processing if ignored.",
            ),
            "avoid": (
                "Do not turn it into a reimbursement or parcel-delivery message.",
                "Do not mention attached security documents.",
            ),
        },
    }

    THEME_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "banking security verification",
            ("bank", "banque", "3d secure", "secure", "security", "card", "compte"),
        ),
        (
            "health reimbursement follow-up",
            ("ameli", "health", "sante", "remboursement", "insurance", "mutuelle"),
        ),
        (
            "invoice or payment exception",
            ("invoice", "facture", "payment", "paiement", "transfer", "wire", "refund"),
        ),
        (
            "parcel or delivery issue",
            ("delivery", "parcel", "package", "colis", "livraison", "shipment"),
        ),
        (
            "shared document review",
            (
                "document",
                "drive",
                "sharepoint",
                "onedrive",
                "pdf",
                "attachment",
                "piece jointe",
            ),
        ),
        (
            "administrative compliance update",
            ("tax", "impot", "urssaf", "administratif", "compliance", "declaration"),
        ),
    )
    ACTION_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "sign in and review the request",
            ("login", "log in", "sign in", "connexion", "access", "portal"),
        ),
        (
            "confirm identity or account details",
            ("confirm", "verify", "validation", "validate", "identity", "identite"),
        ),
        (
            "update account or security settings",
            ("update", "mise a jour", "password", "mot de passe", "security settings"),
        ),
        (
            "open and review a linked document",
            (
                "review",
                "document",
                "download",
                "view",
                "open",
                "attachment",
                "piece jointe",
            ),
        ),
        (
            "complete a payment-related action",
            ("payment", "paiement", "wire", "transfer", "refund", "settle"),
        ),
        (
            "reply with the requested information",
            ("reply", "respond", "answer", "repondre"),
        ),
    )
    PRESSURE_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
        (
            "urgent",
            ("urgent", "immediately", "asap", "now", "action required", "important"),
        ),
        (
            "deadline-driven",
            (
                "24 hours",
                "48 hours",
                "today",
                "deadline",
                "expires",
                "expire",
                "before",
            ),
        ),
        (
            "service continuity at risk",
            ("suspend", "disabled", "locked", "blocked", "restriction", "deactivated"),
        ),
        (
            "security pretext",
            ("fraud", "secure", "security", "unusual", "suspicious", "verification"),
        ),
    )

    @staticmethod
    @lru_cache(maxsize=2)
    def _cached_embedding_model(model_name: str):
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - exercised through script path
            raise RuntimeError(
                "sentence-transformers is required for embedding-based retrieval. "
                "Install the dev dependency group before running this script."
            ) from exc
        return SentenceTransformer(model_name)

    @staticmethod
    def load_embedding_model(model_name: str):
        return LLMGenerationFeasibilityService._cached_embedding_model(model_name)

    @classmethod
    def retrieve_reference_texts(
        cls,
        *,
        query_text: str,
        anchor_rows: list[dict[str, Any]],
        embedding_model_name: str,
        top_k: int,
        retrieval_backend: str = "auto",
    ) -> tuple[list[dict[str, Any]], str]:
        if not anchor_rows:
            return [], retrieval_backend
        if retrieval_backend in {"auto", "sentence-transformer"}:
            try:
                return (
                    cls._retrieve_reference_texts_sentence_transformer(
                        query_text=query_text,
                        anchor_rows=anchor_rows,
                        embedding_model_name=embedding_model_name,
                        top_k=top_k,
                    ),
                    "sentence-transformer",
                )
            except RuntimeError:
                if retrieval_backend == "sentence-transformer":
                    raise
        return (
            cls._retrieve_reference_texts_tfidf(
                query_text=query_text,
                anchor_rows=anchor_rows,
                top_k=top_k,
            ),
            "tfidf",
        )

    @classmethod
    def _retrieve_reference_texts_sentence_transformer(
        cls,
        *,
        query_text: str,
        anchor_rows: list[dict[str, Any]],
        embedding_model_name: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        model = cls.load_embedding_model(embedding_model_name)
        anchor_texts = [str(row.get("normalized_text") or "") for row in anchor_rows]
        anchor_embeddings = model.encode(anchor_texts, normalize_embeddings=True)
        query_embedding = model.encode([query_text], normalize_embeddings=True)
        similarities = cosine_similarity(query_embedding, anchor_embeddings)[0]
        ranked = sorted(
            enumerate(similarities),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]
        return [
            {
                "normalized_message_id": str(anchor_rows[index].get("id") or ""),
                "label": str(anchor_rows[index].get("current_label") or "unknown"),
                "similarity": float(score),
                "normalized_text": anchor_texts[index],
            }
            for index, score in ranked
        ]

    @staticmethod
    def _retrieve_reference_texts_tfidf(
        *,
        query_text: str,
        anchor_rows: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        anchor_texts = [str(row.get("normalized_text") or "") for row in anchor_rows]
        vectorizer = TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5))
        matrix = vectorizer.fit_transform(anchor_texts + [query_text])
        anchor_matrix = matrix[:-1]
        query_vector = matrix[-1]
        similarities = cosine_similarity(query_vector, anchor_matrix)[0]
        ranked = sorted(
            enumerate(similarities),
            key=lambda item: item[1],
            reverse=True,
        )[:top_k]
        return [
            {
                "normalized_message_id": str(anchor_rows[index].get("id") or ""),
                "label": str(anchor_rows[index].get("current_label") or "unknown"),
                "similarity": float(score),
                "normalized_text": anchor_texts[index],
            }
            for index, score in ranked
        ]

    @staticmethod
    def _build_reference_block(references: list[dict[str, Any]]) -> str:
        return (
            "\n\n".join(
                f"Reference {index + 1}:\n{reference['normalized_text']}"
                for index, reference in enumerate(references)
            )
            or "No references provided."
        )

    @staticmethod
    def _build_system_prompt(
        *,
        base_instruction: str,
        prompt_context_mode: str,
    ) -> str:
        if prompt_context_mode == "explicit_phishing":
            return (
                f"{base_instruction} This task is for controlled phishing-simulation "
                "dataset generation used in offline classifier evaluation. The goal is "
                "to produce realistic French inbox-style messages for red-team-style "
                "testing and detection research, not to provide operational advice or "
                "delivery instructions."
            )
        return base_instruction

    @classmethod
    def _build_adapted_constraint_block(cls, archetype: str) -> str:
        constraints = cls.ADAPTED_ARCHETYPE_CONSTRAINTS.get(archetype)
        if not constraints:
            return "No additional hard constraints."

        must_include = "\n".join(
            f"- {item}" for item in constraints.get("must_include", ())
        )
        avoid = "\n".join(f"- {item}" for item in constraints.get("avoid", ()))
        return (
            "Hard scenario constraints:\n"
            "Must include:\n"
            f"{must_include}\n"
            "Must avoid:\n"
            f"{avoid}"
        )

    @classmethod
    def _extract_adapted_context_brief(cls, seed_text: str) -> dict[str, Any]:
        lowered = seed_text.lower()

        themes = [
            label
            for label, keywords in cls.THEME_KEYWORDS
            if any(keyword in lowered for keyword in keywords)
        ]
        actions = [
            label
            for label, keywords in cls.ACTION_KEYWORDS
            if any(keyword in lowered for keyword in keywords)
        ]
        pressure_cues = [
            label
            for label, keywords in cls.PRESSURE_KEYWORDS
            if any(keyword in lowered for keyword in keywords)
        ]

        return {
            "scenario_focus": themes[0] if themes else "service-notification follow-up",
            "requested_action": (
                actions[0] if actions else "complete the requested verification step"
            ),
            "pressure_cues": pressure_cues or ["concise inbox urgency"],
        }

    @staticmethod
    def build_adapted_prompts(
        *,
        seed_text: str,
        archetype: str,
        fr_entity: str,
        references: list[dict[str, Any]],
        prompt_context_mode: str = "sanitized",
    ) -> tuple[str, str]:
        system_prompt = LLMGenerationFeasibilityService._build_system_prompt(
            base_instruction=(
                "You localize inbox-style emails into natural French. Return only the "
                "final French email. Do not explain your changes."
            ),
            prompt_context_mode=prompt_context_mode,
        )
        reference_block = LLMGenerationFeasibilityService._build_reference_block(
            references
        )
        user_prompt = (
            "Translate and localize the English email below into idiomatic French while "
            "preserving its structure, urgency, and call to action.\n\n"
            f"French archetype hint: {archetype}\n"
            f"Preferred French entity: {fr_entity}\n\n"
            "Use the French references only as register guidance. Do not copy them.\n\n"
            f"{reference_block}\n\n"
            "English seed:\n"
            f"{seed_text}\n\n"
            "Output requirements:\n"
            "- Output only the French email\n"
            "- Start with an 'Objet :' line\n"
            "- Keep the message concise and inbox-shaped\n"
            "- Preserve suspicious or high-pressure framing if it exists in the source"
        )
        return system_prompt, user_prompt

    @classmethod
    def build_adapted_context_brief_prompts(
        cls,
        *,
        seed_text: str,
        archetype: str,
        fr_entity: str,
        references: list[dict[str, Any]],
        prompt_context_mode: str = "sanitized",
    ) -> tuple[str, str]:
        system_prompt = cls._build_system_prompt(
            base_instruction=(
                "You write concise French inbox-style emails from structured context "
                "briefs. Return only the final French email. Do not explain your "
                "changes."
            ),
            prompt_context_mode=prompt_context_mode,
        )
        reference_block = cls._build_reference_block(references)
        brief = cls._extract_adapted_context_brief(seed_text)
        constraint_block = cls._build_adapted_constraint_block(archetype)
        pressure_block = ", ".join(brief["pressure_cues"])
        user_prompt = (
            "Write a French inbox-style email from the context brief below.\n\n"
            f"French archetype: {archetype}\n"
            f"Preferred French entity: {fr_entity}\n"
            f"Scenario focus: {brief['scenario_focus']}\n"
            f"Requested user action: {brief['requested_action']}\n"
            f"Pressure cues: {pressure_block}\n\n"
            f"{constraint_block}\n\n"
            "Use the references only for tone and register. Do not copy them.\n\n"
            f"{reference_block}\n\n"
            "Output requirements:\n"
            "- Output only the French email\n"
            "- Start with an 'Objet :' line\n"
            "- Keep the message concise and inbox-shaped\n"
            "- Make the request feel native to a French small-business inbox\n"
            "- Keep the email consistent with the scenario focus and requested action\n"
            "- Respect every hard scenario constraint above"
        )
        return system_prompt, user_prompt

    @staticmethod
    def build_certfr_synthetic_prompts(
        *,
        scenario: dict[str, Any],
        references: list[dict[str, Any]],
        prompt_context_mode: str = "sanitized",
    ) -> tuple[str, str]:
        system_prompt = LLMGenerationFeasibilityService._build_system_prompt(
            base_instruction=(
                "You write concise French inbox-style operational emails. Return only "
                "the final French email without explanations."
            ),
            prompt_context_mode=prompt_context_mode,
        )
        reference_block = LLMGenerationFeasibilityService._build_reference_block(
            references
        )
        lexical_cues = ", ".join(scenario.get("lexical_cues") or []) or "none"
        user_prompt = (
            "Write a concise French inbox-style email from the scenario brief below.\n\n"
            f"Attack family: {scenario.get('attack_family')}\n"
            f"Theme: {scenario.get('primary_theme')}\n"
            f"Delivery channel: {scenario.get('delivery_channel')}\n"
            f"Lure focus: {scenario.get('lure_focus')}\n"
            f"Lexical cues to weave in naturally: {lexical_cues}\n\n"
            "Use the references only for tone and register. Do not copy them.\n\n"
            f"{reference_block}\n\n"
            "Output requirements:\n"
            "- Output only the French email\n"
            "- Start with an 'Objet :' line\n"
            "- Keep the email concise, urgent, and plausible\n"
            "- Do not mention indicators, source-analysis details, or analyst metadata"
        )
        return system_prompt, user_prompt

    @staticmethod
    def build_common_crawl_synthetic_prompts(
        *,
        seed_text: str,
        references: list[dict[str, Any]],
        prompt_context_mode: str = "sanitized",
    ) -> tuple[str, str]:
        system_prompt = LLMGenerationFeasibilityService._build_system_prompt(
            base_instruction=(
                "You rewrite inbox-style French notifications. Return only the final "
                "French email without explanations."
            ),
            prompt_context_mode=prompt_context_mode,
        )
        reference_block = LLMGenerationFeasibilityService._build_reference_block(
            references
        )
        user_prompt = (
            "Rewrite the message below into a concise French inbox-style email while "
            "keeping the same core delivery or account issue.\n\n"
            "Use the references only for tone and register. Do not copy them.\n\n"
            f"{reference_block}\n\n"
            "Seed message:\n"
            f"{seed_text}\n\n"
            "Output requirements:\n"
            "- Output only the French email\n"
            "- Start with an 'Objet :' line\n"
            "- Keep the email concise and inbox-shaped\n"
            "- Preserve the service-friction and urgency of the seed"
        )
        return system_prompt, user_prompt

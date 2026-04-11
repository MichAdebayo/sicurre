from __future__ import annotations

import hashlib
import random
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
from faker import Faker


TemplateFactory = Callable[[], tuple[str, str]]

DEFAULT_TARGET_PER_ARCHETYPE = 300
DEFAULT_PHISHING_LABEL = 1
MIN_SOURCE_TEXT_LENGTH = 50
MAX_SOURCE_TEXT_LENGTH = 5_000

FRENCH_MARKERS: tuple[str, ...] = (
    "vous",
    "votre",
    "veuillez",
    "cordialement",
    "madame",
    "monsieur",
    "bonjour",
    "é",
    "è",
    "ê",
    "ë",
    "à",
    "ù",
    "ç",
    "ô",
)

URGENCY_WORDS: tuple[str, ...] = (
    "urgent",
    "immédiat",
    "délai",
    "suspension",
    "bloqué",
    "pénalité",
)

ARCHETYPES: dict[str, dict[str, str | tuple[str, ...]]] = {
    "dgfip_tax": {
        "fr_entity": "DGFiP — Direction Générale des Finances Publiques",
        "intent": "tax_urgency",
        "en_patterns": (
            r"\btax\b",
            r"\birs\b",
            r"\brefund\b",
            r"tax return",
            r"tax payment",
            r"\baudit\b",
            r"fiscal",
            r"revenue",
            r"tax.*(?:due|owe|overdue)",
            r"(?:federal|state).*tax",
        ),
    },
    "urssaf_cotisation": {
        "fr_entity": "URSSAF — Union de Recouvrement",
        "intent": "contribution_urgency",
        "en_patterns": (
            r"social security",
            r"\bssn\b",
            r"\bcontribution\b",
            r"\bpayroll\b",
            r"employment.*tax",
            r"\bbenefits?\b.*(?:suspend|cancel)",
            r"\bpension\b",
            r"\binsurance.*payment",
        ),
    },
    "ameli_sante": {
        "fr_entity": "Ameli — Assurance Maladie",
        "intent": "health_reimbursement",
        "en_patterns": (
            r"health.*insurance",
            r"\bmedical\b",
            r"\bhealthcare\b",
            r"\bprescription\b",
            r"hospital.*bill",
            r"insurance.*claim",
            r"medical.*record",
            r"\bco-?pay\b",
        ),
    },
    "caf_allocation": {
        "fr_entity": "CAF — Caisse d'Allocations Familiales",
        "intent": "benefit_suspension",
        "en_patterns": (
            r"\ballocation\b",
            r"\bwelfare\b",
            r"\bbenefit\b",
            r"child.*(?:support|benefit)",
            r"housing.*(?:benefit|assistance)",
            r"\bsubsidy\b",
            r"government.*(?:aid|assistance)",
        ),
    },
    "laposte_colis": {
        "fr_entity": "La Poste / Chronopost",
        "intent": "delivery_urgency",
        "en_patterns": (
            r"\bparcel\b",
            r"\bpackage\b",
            r"\bdelivery\b",
            r"\btracking\b",
            r"\bshipment\b",
            r"\busps\b",
            r"\bfedex\b",
            r"\bups\b",
            r"customs.*fee",
            r"\bcourier\b",
            r"\bshipping\b",
        ),
    },
    "banque_securite": {
        "fr_entity": "BNP Paribas / Crédit Agricole / Société Générale",
        "intent": "account_security",
        "en_patterns": (
            r"\bbank\b",
            r"\baccount.*(?:suspend|lock|restrict|verif)",
            r"\btransaction\b",
            r"\bunauthori[sz]ed\b",
            r"\bfraud\b",
            r"credit.*card",
            r"\batm\b",
            r"\bpin\b",
            r"(?:verify|confirm).*(?:identity|account)",
        ),
    },
    "franceconnect_id": {
        "fr_entity": "FranceConnect / Service-Public.fr",
        "intent": "credential_theft",
        "en_patterns": (
            r"(?:verify|confirm).*identity",
            r"\blogin.*(?:attempt|suspicious)",
            r"\bpassword.*(?:reset|expire|change)",
            r"\bcredential\b",
            r"two.?factor",
            r"\bauthenticat",
            r"\bunusual.*(?:activity|sign)",
        ),
    },
    "facture_paiement": {
        "fr_entity": "EDF / SFR / Orange / Free",
        "intent": "invoice_urgency",
        "en_patterns": (
            r"\binvoice\b",
            r"\bpayment.*(?:due|overdue|fail)",
            r"\bbill\b.*(?:pay|due|unpaid)",
            r"\bsubscription\b",
            r"service.*(?:suspend|cancel|terminat)",
            r"\brenew\b",
            r"\boutstanding.*(?:balance|amount)",
        ),
    },
}

EXPORT_COLUMNS: list[str] = [
    "text",
    "label",
    "source",
    "language",
    "archetype",
    "fr_entity",
    "en_source_hash",
    "en_source_dataset",
    "en_source_raw_record_id",
    "text_hash",
]


@dataclass(frozen=True, slots=True)
class AdaptationExportResult:
    dataframe: pd.DataFrame
    timestamped_path: Path
    stable_path: Path


@dataclass(frozen=True, slots=True)
class AdaptationSummary:
    total_rows: int
    matched_rows: int
    matched_ratio: float
    per_archetype_matches: dict[str, int]
    generated_per_archetype: dict[str, int]
    deduplicated_rows: int
    removed_duplicates: int
    mean_text_length: float
    min_french_markers: int
    mean_french_markers: float
    urgency_ratio: float


class FrenchCulturalAdaptationService:
    def __init__(self, seed: int = 42) -> None:
        self.seed = seed
        self.random = random.Random(seed)
        self.fake = Faker("fr_FR")
        self.fake.seed_instance(seed)

    def load_phishing_corpus(
        self,
        corpus_path: Path,
        *,
        phishing_label: int = DEFAULT_PHISHING_LABEL,
    ) -> pd.DataFrame:
        dataframe = pd.read_csv(corpus_path)
        phishing_df = dataframe[dataframe["label"] == phishing_label].copy()
        phishing_df = phishing_df.dropna(subset=["text"])
        phishing_df["text_len"] = phishing_df["text"].astype(str).str.len()
        phishing_df = phishing_df[
            (phishing_df["text_len"] >= MIN_SOURCE_TEXT_LENGTH)
            & (phishing_df["text_len"] <= MAX_SOURCE_TEXT_LENGTH)
        ].reset_index(drop=True)
        return phishing_df

    def match_archetypes(self, text: str, min_hits: int = 2) -> list[str]:
        lowered_text = text.lower()
        matched: list[str] = []
        for name, archetype in ARCHETYPES.items():
            patterns = archetype["en_patterns"]
            hits = sum(
                1
                for pattern in patterns
                if isinstance(pattern, str) and re.search(pattern, lowered_text)
            )
            if hits >= min_hits:
                matched.append(name)
        return matched

    def attach_archetype_matches(self, phishing_df: pd.DataFrame) -> pd.DataFrame:
        matched_df = phishing_df.copy()
        matched_df["archetypes"] = (
            matched_df["text"].astype(str).apply(self.match_archetypes)
        )
        matched_df["n_archetypes"] = matched_df["archetypes"].apply(len)
        return matched_df

    def per_archetype_match_counts(self, matched_df: pd.DataFrame) -> dict[str, int]:
        counts: Counter[str] = Counter()
        for archetypes in matched_df["archetypes"]:
            for archetype in archetypes:
                counts[archetype] += 1
        return dict(counts)

    def generate_all_adapted_emails(
        self,
        matched_df: pd.DataFrame,
        *,
        target_per_archetype: int = DEFAULT_TARGET_PER_ARCHETYPE,
    ) -> pd.DataFrame:
        rows: list[dict[str, str | int]] = []
        for archetype, templates in self.template_map.items():
            rows.extend(
                self.generate_for_archetype(
                    matched_df,
                    archetype,
                    templates,
                    target_count=target_per_archetype,
                )
            )
        return pd.DataFrame(rows)

    def generate_for_archetype(
        self,
        matched_df: pd.DataFrame,
        archetype: str,
        templates: list[TemplateFactory],
        *,
        target_count: int,
    ) -> list[dict[str, str | int]]:
        mask = matched_df["archetypes"].apply(lambda items: archetype in items)
        english_pool = matched_df[mask].reset_index(drop=True)

        rows: list[dict[str, str | int]] = []
        for _ in range(target_count):
            if not english_pool.empty:
                sample_index = self.random.randrange(len(english_pool))
                source_row = english_pool.iloc[sample_index]
                source_hash = hashlib.sha256(
                    str(source_row["text"]).encode("utf-8")
                ).hexdigest()[:16]
                source_dataset = str(source_row.get("source", "unknown"))
                source_raw_record_id = str(source_row.get("raw_record_id") or "unknown")
            else:
                source_hash = "no_match"
                source_dataset = "template_only"
                source_raw_record_id = "template_only"

            subject, body = self.random.choice(templates)()
            full_text = f"Objet : {subject}\n\n{body}"
            rows.append(
                {
                    "text": full_text,
                    "label": DEFAULT_PHISHING_LABEL,
                    "source": "adapted_en_fr",
                    "language": "fr",
                    "archetype": archetype,
                    "fr_entity": str(ARCHETYPES[archetype]["fr_entity"]),
                    "en_source_hash": source_hash,
                    "en_source_dataset": source_dataset,
                    "en_source_raw_record_id": source_raw_record_id,
                }
            )
        return rows

    def deduplicate_generated(
        self, adapted_df: pd.DataFrame
    ) -> tuple[pd.DataFrame, int]:
        deduplicated_df = adapted_df.copy()
        deduplicated_df["text_hash"] = (
            deduplicated_df["text"]
            .astype(str)
            .apply(lambda text: hashlib.sha256(text.encode("utf-8")).hexdigest())
        )
        before = len(deduplicated_df)
        deduplicated_df = deduplicated_df.drop_duplicates(
            subset=["text_hash"]
        ).reset_index(drop=True)
        return deduplicated_df, before - len(deduplicated_df)

    def build_summary(
        self,
        source_df: pd.DataFrame,
        matched_df: pd.DataFrame,
        adapted_df: pd.DataFrame,
        *,
        removed_duplicates: int,
    ) -> AdaptationSummary:
        matched_rows = int((matched_df["n_archetypes"] > 0).sum())
        per_archetype_matches = self.per_archetype_match_counts(matched_df)
        generated_per_archetype = {
            str(name): int(count)
            for name, count in adapted_df["archetype"].value_counts().items()
        }

        scored_df = adapted_df.copy()
        scored_df["text_len"] = scored_df["text"].astype(str).str.len()
        scored_df["fr_score"] = scored_df["text"].astype(str).apply(self.french_score)
        scored_df["has_urgency"] = (
            scored_df["text"].astype(str).apply(self.has_urgency_marker)
        )

        return AdaptationSummary(
            total_rows=len(source_df),
            matched_rows=matched_rows,
            matched_ratio=(matched_rows / len(source_df) if len(source_df) else 0.0),
            per_archetype_matches=per_archetype_matches,
            generated_per_archetype=generated_per_archetype,
            deduplicated_rows=len(scored_df),
            removed_duplicates=removed_duplicates,
            mean_text_length=(
                float(scored_df["text_len"].mean()) if len(scored_df) else 0.0
            ),
            min_french_markers=(
                int(scored_df["fr_score"].min()) if len(scored_df) else 0
            ),
            mean_french_markers=(
                float(scored_df["fr_score"].mean()) if len(scored_df) else 0.0
            ),
            urgency_ratio=(
                float(scored_df["has_urgency"].mean()) if len(scored_df) else 0.0
            ),
        )

    def export_adapted_dataframe(
        self,
        adapted_df: pd.DataFrame,
        output_dir: Path,
    ) -> AdaptationExportResult:
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        timestamped_path = (
            output_dir / f"adapted_fr_phishing_{len(adapted_df)}_{timestamp}.csv"
        )
        stable_path = output_dir / "adapted_fr_phishing.csv"
        adapted_df[EXPORT_COLUMNS].to_csv(
            timestamped_path, index=False, encoding="utf-8"
        )
        adapted_df[EXPORT_COLUMNS].to_csv(stable_path, index=False, encoding="utf-8")
        return AdaptationExportResult(
            dataframe=adapted_df,
            timestamped_path=timestamped_path,
            stable_path=stable_path,
        )

    def french_score(self, text: str) -> int:
        lowered_text = text.lower()
        return sum(1 for marker in FRENCH_MARKERS if marker in lowered_text)

    def has_urgency_marker(self, text: str) -> bool:
        lowered_text = text.lower()
        return any(word in lowered_text for word in URGENCY_WORDS)

    def _ref(self) -> str:
        return f"{self.random.choice(['REF', 'DOS', 'N°'])}-{self.fake.numerify('####-####-##')}"

    def _amount(self) -> str:
        value = round(self.random.uniform(47.50, 2850.00), 2)
        return f"{value:,.2f} €".replace(",", " ").replace(".", ",")

    def _date_fr(self) -> str:
        return self.fake.date_between(start_date="-30d", end_date="+15d").strftime(
            "%d/%m/%Y"
        )

    def _deadline(self) -> str:
        return f"{self.random.choice([24, 48, 72])} heures"

    def _phone_fr(self) -> str:
        return self.fake.phone_number()

    def _pick(self, *options: str) -> str:
        return self.random.choice(options)

    @property
    def template_map(self) -> dict[str, list[TemplateFactory]]:
        return {
            "dgfip_tax": [
                self._dgfip_tax_notice,
                self._dgfip_refund,
                self._dgfip_audit,
            ],
            "urssaf_cotisation": [
                self._urssaf_regularisation,
                self._urssaf_update,
            ],
            "ameli_sante": [
                self._ameli_refund,
                self._ameli_carte_vitale,
            ],
            "caf_allocation": [
                self._caf_suspension,
                self._caf_exceptional_payment,
            ],
            "laposte_colis": [
                self._laposte_delivery,
                self._chronopost_customs,
            ],
            "banque_securite": [
                self._bank_unusual_login,
                self._bank_suspicious_transfer,
                self._bank_3d_secure,
            ],
            "franceconnect_id": [
                self._franceconnect_suspicious_login,
                self._service_public_identity_check,
            ],
            "facture_paiement": [
                self._invoice_suspension,
                self._edf_regularisation,
            ],
        }

    def _dgfip_tax_notice(self) -> tuple[str, str]:
        return (
            f"Avis d'imposition — Erreur détectée sur votre déclaration {self._ref()}",
            (
                f"Madame, Monsieur {self.fake.last_name()},\n\n"
                f"Nous avons détecté une anomalie sur votre déclaration de revenus (dossier {self._ref()}). "
                f"Un montant de {self._amount()} reste dû au titre de l'exercice fiscal 2025.\n\n"
                f"Veuillez régulariser votre situation avant le {self._date_fr()} en accédant à votre espace personnel sur impots-gouv-fr.com.\n\n"
                f"En l'absence de régularisation dans un délai de {self._deadline()}, des pénalités de retard seront appliquées.\n\n"
                f"Direction Générale des Finances Publiques\nService des Impôts des Particuliers\nTél : {self._phone_fr()}"
            ),
        )

    def _dgfip_refund(self) -> tuple[str, str]:
        return (
            self._pick(
                "Remboursement fiscal en attente — Action requise",
                "DGFiP — Confirmez votre remboursement fiscal",
                "Validation requise pour votre remboursement d'impôt",
            ),
            (
                f"Cher(e) contribuable,\n\n"
                f"Suite au traitement de votre déclaration de revenus, nous avons constaté un trop-perçu de {self._amount()} en votre faveur.\n\n"
                f"Pour recevoir votre remboursement, veuillez confirmer vos coordonnées bancaires avant le {self._date_fr()}.\n\n"
                f"→ Confirmer mon remboursement : https://dgfip-remboursement.fr/{self.fake.lexify('????????')}\n\n"
                f"Ce lien est valable {self._deadline()}.\n\nDGFiP — Direction Générale des Finances Publiques"
            ),
        )

    def _dgfip_audit(self) -> tuple[str, str]:
        return (
            f"Contrôle fiscal — Convocation {self._ref()}",
            (
                "Madame, Monsieur,\n\n"
                f"Dans le cadre d'un contrôle fiscal portant sur les années 2023-2025, nous vous informons que votre dossier (réf. {self._ref()}) a été sélectionné pour vérification.\n\n"
                f"Veuillez transmettre les justificatifs demandés sous {self._deadline()} :\n"
                f"https://impots-verification.gouv.fr/{self.fake.lexify('??????')}\n\n"
                "Tout retard entraînera une majoration de 10 % du montant dû.\n\nService de Vérification Comptable\nDGFiP"
            ),
        )

    def _urssaf_regularisation(self) -> tuple[str, str]:
        return (
            f"Régularisation urgente de vos cotisations — {self._ref()}",
            (
                f"Madame, Monsieur {self.fake.last_name()},\n\n"
                f"Nous constatons un retard de paiement de vos cotisations sociales (montant : {self._amount()}).\n\n"
                f"Votre numéro de cotisant : {self.fake.numerify('### ### ### ###')}\n"
                f"Date limite de régularisation : {self._date_fr()}\n\n"
                f"Sans régularisation dans les {self._deadline()}, votre dossier sera transmis au service de recouvrement forcé.\n\n"
                f"Régularisez votre situation :\nhttps://urssaf-regul.fr/{self.fake.lexify('????????')}\n\nURSSAF — Service Recouvrement"
            ),
        )

    def _urssaf_update(self) -> tuple[str, str]:
        return (
            self._pick(
                "Mise à jour obligatoire — Espace URSSAF",
                "URSSAF — Vérification requise sur votre espace",
                "Contrôle de vos informations URSSAF en attente",
            ),
            (
                "Bonjour,\n\n"
                "Suite à une mise à jour de notre système, nous vous demandons de vérifier vos informations personnelles et bancaires sur votre espace URSSAF.\n\n"
                "Cette vérification est obligatoire pour maintenir votre couverture sociale en tant qu'auto-entrepreneur.\n\n"
                f"→ Accéder à mon espace : https://mon-urssaf-verification.fr/{self.fake.lexify('??????')}\n\n"
                f"Date limite : {self._date_fr()}\n\nCordialement,\nURSSAF Île-de-France"
            ),
        )

    def _ameli_refund(self) -> tuple[str, str]:
        return (
            f"Remboursement Ameli en attente — {self._amount()}",
            (
                "Cher(e) assuré(e),\n\n"
                f"Nous avons le plaisir de vous informer qu'un remboursement de {self._amount()} est en attente sur votre compte Ameli.\n\n"
                f"Pour finaliser ce remboursement, veuillez mettre à jour vos coordonnées bancaires dans les {self._deadline()} via le lien suivant :\n\n"
                f"https://ameli-remboursement.fr/{self.fake.lexify('????????')}\n\n"
                f"Numéro de sécurité sociale : {self.fake.numerify('# ## ## ## ### ### ##')}\n\n"
                "L'Assurance Maladie — Ameli.fr"
            ),
        )

    def _ameli_carte_vitale(self) -> tuple[str, str]:
        return (
            self._pick(
                "Renouvellement obligatoire de votre Carte Vitale",
                "Carte Vitale expirée — Mise à jour requise",
                "Ameli — Vérifiez le renouvellement de votre Carte Vitale",
            ),
            (
                f"Madame, Monsieur {self.fake.last_name()},\n\n"
                f"Votre Carte Vitale arrive à expiration le {self._date_fr()}. Pour éviter toute interruption de vos remboursements de soins, veuillez renouveler votre carte en ligne.\n\n"
                f"→ Renouveler ma Carte Vitale : https://ameli-cartevitale.fr/{self.fake.lexify('??????')}\n\n"
                "Vous devrez fournir :\n- Une pièce d'identité en cours de validité\n- Votre RIB\n- Votre numéro de sécurité sociale\n\nCPAM — Caisse Primaire d'Assurance Maladie"
            ),
        )

    def _caf_suspension(self) -> tuple[str, str]:
        return (
            self._pick(
                "Suspension de vos allocations — Action immédiate requise",
                "CAF — Votre dossier risque une suspension immédiate",
                "Déclaration CAF manquante — Régularisation urgente",
            ),
            (
                f"Madame, Monsieur {self.fake.last_name()},\n\n"
                f"Nous vous informons que vos allocations seront suspendues à compter du {self._date_fr()} en raison d'un défaut de déclaration trimestrielle.\n\n"
                f"Pour éviter la suspension, complétez votre déclaration dans les {self._deadline()} :\n"
                f"https://caf-declaration.fr/{self.fake.lexify('????????')}\n\n"
                f"Numéro d'allocataire : {self.fake.numerify('#######')}\n\nCAF — Caisse d'Allocations Familiales"
            ),
        )

    def _caf_exceptional_payment(self) -> tuple[str, str]:
        return (
            self._pick(
                "Versement exceptionnel CAF — Confirmez vos coordonnées",
                "CAF — Validation requise pour votre versement exceptionnel",
                "Paiement CAF en attente — Confirmez vos informations",
            ),
            (
                "Bonjour,\n\n"
                f"Dans le cadre des mesures de soutien au pouvoir d'achat, vous êtes éligible à un versement exceptionnel de {self._amount()}.\n\n"
                f"Pour recevoir ce versement, confirmez votre identité et vos coordonnées bancaires avant le {self._date_fr()} :\n\n"
                f"→ https://caf-versement-exceptionnel.fr/{self.fake.lexify('??????')}\n\nCordialement,\nCAF Nationale"
            ),
        )

    def _laposte_delivery(self) -> tuple[str, str]:
        return (
            f"Votre colis n'a pas pu être livré — {self._ref()}",
            (
                f"Bonjour {self.fake.first_name()},\n\n"
                f"Votre colis (n° {self.fake.numerify('## ### ### ####')}) est en attente au centre de tri. La livraison a échoué en raison d'une adresse incomplète.\n\n"
                "Pour reprogrammer la livraison, des frais de réexpédition de 1,99 € sont à régler :\n"
                f"https://laposte-suivi.fr/{self.fake.lexify('????????')}\n\n"
                f"Sans action de votre part sous {self._deadline()}, le colis sera retourné à l'expéditeur.\n\nLa Poste — Service Colis"
            ),
        )

    def _chronopost_customs(self) -> tuple[str, str]:
        return (
            self._pick(
                "Chronopost — Frais de douane à régler",
                "Chronopost — Régularisation douanière requise",
                "Votre colis Chronopost reste bloqué en douane",
            ),
            (
                "Madame, Monsieur,\n\n"
                f"Votre colis international (réf. {self._ref()}) est bloqué en douane. Des frais de {self._amount()} sont à régler pour le dédouanement.\n\n"
                f"Réglez les frais de douane :\nhttps://chronopost-douane.fr/{self.fake.lexify('??????')}\n\n"
                f"Délai : {self._deadline()} avant retour à l'expéditeur.\n\nChronopost — Service Douane"
            ),
        )

    def _bank_unusual_login(self) -> tuple[str, str]:
        bank_name = self.random.choice(
            [
                "BNP Paribas",
                "Crédit Agricole",
                "Société Générale",
                "LCL",
                "Banque Populaire",
            ]
        )
        return (
            self._pick(
                "Alerte sécurité — Connexion inhabituelle à votre compte",
                "Tentative de connexion inhabituelle — Vérification requise",
                f"{bank_name} — Accès suspect détecté sur votre espace",
            ),
            (
                "Cher(e) client(e),\n\n"
                f"Nous avons détecté une tentative de connexion inhabituelle à votre compte {bank_name} depuis une adresse IP non reconnue ({self.fake.ipv4()}).\n\n"
                "Si vous n'êtes pas à l'origine de cette connexion, veuillez sécuriser votre compte immédiatement :\n"
                f"https://ma-banque-securite.fr/{self.fake.lexify('????????')}\n\n"
                f"En l'absence de vérification sous {self._deadline()}, votre compte sera temporairement bloqué.\n\nService Fraude & Sécurité"
            ),
        )

    def _bank_suspicious_transfer(self) -> tuple[str, str]:
        bank_name = self.random.choice(
            ["BNP Paribas", "Crédit Agricole", "Société Générale"]
        )
        return (
            self._pick(
                "Virement suspect détecté — Validation requise",
                "Validation urgente d'un virement suspect",
                f"{bank_name} — Opposition requise sur un virement en cours",
            ),
            (
                f"Bonjour {self.fake.last_name()},\n\n"
                f"Un virement de {self._amount()} vers un compte étranger (IBAN: {self.fake.lexify('??').upper()}{self.fake.numerify('## #### #### #### #### ####')}) a été initié depuis votre compte.\n\n"
                "Si vous n'avez pas autorisé cette opération, bloquez-la immédiatement :\n"
                f"https://securite-bancaire.fr/{self.fake.lexify('??????')}\n\n"
                f"Vous disposez de {self._deadline()} pour contester ce virement.\n\nService Opposition — {bank_name}"
            ),
        )

    def _bank_3d_secure(self) -> tuple[str, str]:
        bank_name = self.random.choice(
            ["BNP Paribas", "Crédit Agricole", "Société Générale", "CIC"]
        )
        return (
            self._pick(
                "Mise à jour 3D Secure obligatoire",
                "Authentification 3D Secure à confirmer",
                f"{bank_name} — Mise à jour 3D Secure requise",
            ),
            (
                "Madame, Monsieur,\n\n"
                f"Conformément à la directive européenne DSP2, vous devez mettre à jour votre dispositif d'authentification 3D Secure avant le {self._date_fr()}.\n\n"
                "Sans cette mise à jour, vos paiements en ligne seront refusés.\n\n"
                f"→ Mettre à jour 3D Secure : https://3dsecure-validation.fr/{self.fake.lexify('????????')}\n\n"
                f"Banque {bank_name}\nService Monétique"
            ),
        )

    def _franceconnect_suspicious_login(self) -> tuple[str, str]:
        return (
            self._pick(
                "Tentative de connexion suspecte — FranceConnect",
                "FranceConnect — Vérification de sécurité requise",
                "FranceConnect — Activité inhabituelle sur votre identité numérique",
            ),
            (
                "Bonjour,\n\n"
                f"Une tentative de connexion à votre compte FranceConnect a été détectée le {self._date_fr()} à {self.random.randint(1, 23)}h{self.random.randint(10, 59)} depuis {self.random.choice(['Russie', 'Nigeria', 'Turquie', 'Chine', 'Roumanie'])}.\n\n"
                "Si vous n'êtes pas à l'origine de cette connexion, sécurisez immédiatement votre compte :\n"
                f"https://franceconnect-securite.fr/{self.fake.lexify('????????')}\n\n"
                f"Votre identité numérique est en danger. Agissez dans les {self._deadline()}.\n\nFranceConnect — Sécurité des Identités Numériques"
            ),
        )

    def _service_public_identity_check(self) -> tuple[str, str]:
        return (
            self._pick(
                "Vérification d'identité obligatoire — Service-Public.fr",
                "Service-Public.fr — Contrôle d'identité en attente",
                "Maintien de vos services publics — Vérification requise",
            ),
            (
                f"Madame, Monsieur {self.fake.last_name()},\n\n"
                "Dans le cadre du renforcement de la sécurité numérique, une vérification de votre identité est requise pour maintenir l'accès à vos services publics en ligne.\n\n"
                "Documents requis :\n- Carte d'identité ou passeport (recto/verso)\n- Justificatif de domicile récent\n- Avis d'imposition 2025\n\n"
                f"→ Vérifier mon identité : https://service-public-id.fr/{self.fake.lexify('??????')}\n\n"
                f"Date limite : {self._date_fr()}\n\nDirection de l'Information Légale et Administrative"
            ),
        )

    def _invoice_suspension(self) -> tuple[str, str]:
        operator_name = self.random.choice(
            ["SFR", "Orange", "Free", "Bouygues Telecom"]
        )
        return (
            f"Facture impayée — Suspension de votre ligne {operator_name}",
            (
                "Madame, Monsieur,\n\n"
                f"Malgré nos relances, votre facture du {self._date_fr()} d'un montant de {self._amount()} reste impayée.\n\n"
                f"Sans réglement dans les {self._deadline()}, votre ligne sera suspendue et votre dossier transmis à un organisme de recouvrement.\n\n"
                f"Réglez votre facture en ligne :\nhttps://facture-paiement.fr/{self.fake.lexify('????????')}\n\n"
                f"Référence client : {self._ref()}\n\nService Recouvrement"
            ),
        )

    def _edf_regularisation(self) -> tuple[str, str]:
        signature = self._pick(
            "EDF — Cellule facturation",
            "EDF — Service contrats",
            "EDF — Assistance facturation",
        )
        return (
            self._pick(
                "EDF — Régularisation annuelle de votre contrat",
                "EDF — Solde annuel à régler sur votre contrat",
                "Votre contrat EDF nécessite une régularisation immédiate",
            ),
            (
                "Cher(e) client(e),\n\n"
                f"Suite à la régularisation annuelle de votre contrat d'électricité, un solde de {self._amount()} est à régler avant le {self._date_fr()}.\n\n"
                f"Numéro de contrat : {self.fake.numerify('#### #### ####')}\n"
                f"Point de livraison : {self.fake.numerify('## ### ### ### ### ###')}\n\n"
                f"→ Payer ma facture : https://edf-regularisation.fr/{self.fake.lexify('??????')}\n\n"
                f"En cas de non-paiement, une coupure d'alimentation électrique pourra être programmée.\n\n{signature}"
            ),
        )

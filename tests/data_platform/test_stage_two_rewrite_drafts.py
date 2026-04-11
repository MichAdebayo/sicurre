from __future__ import annotations

from data_platform.services.stage_two_rewrite_drafts import StageTwoRewriteDraftService


def test_stage_two_rewrite_drafts_builds_usable_legitimate_notification() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-1",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "abc",
                    "source_preview": "A réception de mail, de sms ou d'appels douteux, ne renseignez jamais vos données bancaires et personnelles.",
                }
            ]
        }
    )

    assert drafts["draft_count"] == 1
    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "Bonjour" in draft["body"]
    assert "service client" in draft["body"].lower()


def test_stage_two_rewrite_drafts_builds_french_repaired_spam() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-2",
                    "source_name": "database-historical",
                    "rule_key": "historical_repair_needed",
                    "rewrite_mode": "repair_then_rewrite",
                    "target_label": "spam",
                    "raw_record_id": "hist-1",
                    "source_preview": "Objet : WELCOME BONUS 2000€ + 100 FREE SPINS Pending in your Account",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "2000 €" in draft["subject"]
    assert "100 tours gratuits" in draft["body"]


def test_stage_two_rewrite_drafts_marks_empty_source_as_drop() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-3",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "empty-1",
                    "source_preview": "",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "drop"
    assert "insufficient_source_context" in draft["review_notes"]


def test_stage_two_rewrite_drafts_downgrades_duplicate_outputs() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-a",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "dup-a",
                    "source_preview": "Veuillez sécuriser votre accès à votre compte dès aujourd'hui.",
                },
                {
                    "job_id": "job-b",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "dup-b",
                    "source_preview": "Veuillez sécuriser votre accès à votre compte dès aujourd'hui.",
                },
            ]
        }
    )

    for draft in drafts["drafts"]:
        assert draft["review_state"] == "usable"
        assert "duplicate_generated_draft" in draft["review_notes"]


def test_stage_two_rewrite_drafts_keeps_distinct_legitimate_previews_distinct() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-legit-a",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "legit-a",
                    "source_preview": "A réception de mail, de sms ou d'appels douteux, ne renseignez jamais vos données bancaires et personnelles.",
                },
                {
                    "job_id": "job-legit-b",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "legit-b",
                    "source_preview": "Si vous devez réinitialiser votre accès, utilisez uniquement votre espace habituel et attendez le code temporaire transmis par SMS.",
                },
            ]
        }
    )

    assert drafts["drafts"][0]["text_sha256"] != drafts["drafts"][1]["text_sha256"]
    assert all(
        "duplicate_generated_draft" not in draft["review_notes"]
        for draft in drafts["drafts"]
    )


def test_stage_two_rewrite_drafts_keeps_distinct_promotional_previews_distinct() -> (
    None
):
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-promo-a",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "promotional_spam",
                    "rewrite_mode": "promotional_page_to_spam_message",
                    "target_label": "spam",
                    "raw_record_id": "promo-a",
                    "source_preview": "Mon Assurance Santé au prix juste avec des garanties adaptées à votre profil et une réponse rapide.",
                },
                {
                    "job_id": "job-promo-b",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "promotional_spam",
                    "rewrite_mode": "promotional_page_to_spam_message",
                    "target_label": "spam",
                    "raw_record_id": "promo-b",
                    "source_preview": "Le programme de cashback vous permet de récupérer une partie de vos achats et d'activer votre cagnotte fidélité.",
                },
            ]
        }
    )

    assert drafts["drafts"][0]["text_sha256"] != drafts["drafts"][1]["text_sha256"]
    assert all(draft["review_state"] == "usable" for draft in drafts["drafts"])


def test_stage_two_rewrite_drafts_downgrades_page_like_legitimate_subject() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-page-like",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "page-like-1",
                    "source_preview": "Tous les champs sont obligatoires. Merci de vérifier les informations demandées avant validation depuis votre espace habituel.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "needs_prompt_tuning"
    assert "page_like_legitimate_subject" in draft["review_notes"]


def test_stage_two_rewrite_drafts_downgrades_fragment_like_legitimate_subject() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-fragment-like",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "fragment-like-1",
                    "source_preview": "15 €/min + prix de l’appel pour poursuivre la demande en ligne et confirmer votre espace habituel aujourd'hui.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "needs_prompt_tuning"
    assert "fragment_like_legitimate_subject" in draft["review_notes"]


def test_stage_two_rewrite_drafts_falls_back_from_page_like_focus_phrase() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-page-focus",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "page-focus-1",
                    "source_preview": "# paiement Service e-Carte Bleue. Vous recevrez une notification sur votre messagerie sécurisée après validation.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert "page_like_legitimate_subject" not in draft["review_notes"]
    assert draft["review_state"] == "usable"


def test_stage_two_rewrite_drafts_rejects_pdf_title_fragment_focus() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-pdf-fragment",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "pdf-fragment-1",
                    "source_preview": "Découvrez les essentiels de Certicode Plus (pdf) et les notifications associées à votre espace sécurisé.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "(pdf" not in draft["subject"].lower()
    assert (
        "certicode" in draft["subject"].lower()
        or "authentification" in draft["subject"].lower()
    )


def test_stage_two_rewrite_drafts_rejects_imperative_fragment_focus() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-imperative-fragment",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "imperative-fragment-1",
                    "source_preview": "Pour faire un virement, cliquez de la messagerie sécurisée et confirmez votre accès depuis votre espace habituel.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "cliquez" not in draft["subject"].lower()
    assert not draft["subject"].lower().endswith(" de")


def test_stage_two_rewrite_drafts_avoids_scam_report_scaffold_in_legitimate_subject() -> (
    None
):
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-scaffold-focus",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "scaffold-focus-1",
                    "source_preview": "Ne manquez pas cette vidéo choc. En Savoir + Arnaques classées par catégories. Arnaques par SMS et arnaques via Paylib signalées cette semaine.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "en savoir" not in draft["subject"].lower()
    assert "arnaques classées" not in draft["subject"].lower()


def test_stage_two_rewrite_drafts_falls_back_from_fragment_like_awareness_topic() -> (
    None
):
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-awareness-fragment",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "awareness_or_report",
                    "rewrite_mode": "awareness_page_to_warning_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "awareness-fragment-1",
                    "source_preview": "Serious Game A la fois ludique et pédagogique pour sensibiliser aux arnaques par mail et sms.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "serious game" not in draft["subject"].lower()
    assert draft["subject"].lower().endswith("les messages suspects")


def test_stage_two_rewrite_drafts_falls_back_from_how_to_awareness_title() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-awareness-howto",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "awareness_or_report",
                    "rewrite_mode": "awareness_page_to_warning_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "awareness-howto-1",
                    "source_preview": "Comment reconnaître un appel frauduleux et éviter de divulguer vos données bancaires par téléphone.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "comment reconnaître" not in draft["subject"].lower()
    assert "appels frauduleux" in draft["subject"].lower()


def test_stage_two_rewrite_drafts_contracts_awareness_articles() -> None:
    assert (
        StageTwoRewriteDraftService._prepend_topic_preposition(
            "les appels frauduleux", "à"
        )
        == "aux appels frauduleux"
    )
    assert (
        StageTwoRewriteDraftService._prepend_topic_preposition(
            "les messages suspects", "de"
        )
        == "des messages suspects"
    )


def test_stage_two_rewrite_drafts_avoids_first_person_delivery_subject() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-first-person-delivery",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "instructional_legitimate",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "first-person-delivery-1",
                    "source_preview": "Je viens de recevoir un SMS de Mondial Relay indiquant qu'un colis ne peut pas être livré sans nouvelle confirmation du point relais aujourd'hui.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "je viens de recevoir" not in draft["subject"].lower()
    assert (
        "livraison" in draft["subject"].lower() or "colis" in draft["subject"].lower()
    )


def test_stage_two_rewrite_drafts_builds_awareness_warning_notification() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-aware-1",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "awareness_or_report",
                    "rewrite_mode": "awareness_page_to_warning_notification",
                    "target_label": "legitimate",
                    "raw_record_id": "aware-1",
                    "source_preview": "Comment reconnaître un appel frauduleux ? La Banque Postale vous conseille de faire preuve de vigilance en cas d'appel suspect et de ne jamais divulguer vos informations personnelles.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "appel" in draft["subject"].lower()
    assert "vigil" in draft["body"].lower() or "par téléphone" in draft["body"].lower()


def test_stage_two_rewrite_drafts_builds_distinct_phishing_lures() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-phish-a",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "phishing_lure_candidate",
                    "rewrite_mode": "embedded_lure_to_phishing_email",
                    "target_label": "phishing",
                    "raw_record_id": "phish-a",
                    "source_preview": "Distribution-retard.com Page miroir Mondial Relay. Message reçu ce jour indiquant qu'un colis ne peut pas être livré sans confirmation de l'adresse.",
                },
                {
                    "job_id": "job-phish-b",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "phishing_lure_candidate",
                    "rewrite_mode": "embedded_lure_to_phishing_email",
                    "target_label": "phishing",
                    "raw_record_id": "phish-b",
                    "source_preview": "Alerte signalée : faux suivi de livraison demandant de confirmer un colis en attente et de finaliser la reprogrammation aujourd'hui.",
                },
            ]
        }
    )

    first, second = drafts["drafts"]
    assert first["review_state"] == "usable"
    assert second["review_state"] == "usable"
    assert first["text_sha256"] != second["text_sha256"]
    assert "duplicate_generated_draft" not in first["review_notes"]
    assert "duplicate_generated_draft" not in second["review_notes"]
    assert (
        "livraison" in first["subject"].lower() or "colis" in first["subject"].lower()
    )
    assert (
        "vérification" in first["body"].lower() or "confirmer" in first["body"].lower()
    )


def test_stage_two_rewrite_drafts_downgrades_duplicate_phishing_lures() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-phish-dup-a",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "phishing_lure_candidate",
                    "rewrite_mode": "embedded_lure_to_phishing_email",
                    "target_label": "phishing",
                    "raw_record_id": "phish-dup-a",
                    "source_preview": "Distribution-retard.com Page miroir Mondial Relay. Message reçu ce jour indiquant qu'un colis ne peut pas être livré sans confirmation de l'adresse.",
                },
                {
                    "job_id": "job-phish-dup-b",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "phishing_lure_candidate",
                    "rewrite_mode": "embedded_lure_to_phishing_email",
                    "target_label": "phishing",
                    "raw_record_id": "phish-dup-b",
                    "source_preview": "Distribution-retard.com Page miroir Mondial Relay. Message reçu ce jour indiquant qu'un colis ne peut pas être livré sans confirmation de l'adresse.",
                },
            ]
        }
    )

    assert all(draft["review_state"] == "usable" for draft in drafts["drafts"])
    assert all(
        "duplicate_generated_draft" in draft["review_notes"]
        for draft in drafts["drafts"]
    )


def test_stage_two_rewrite_drafts_extracts_specific_promotional_topic() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-promo-specific",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "promotional_spam",
                    "rewrite_mode": "promotional_page_to_spam_message",
                    "target_label": "spam",
                    "raw_record_id": "promo-specific",
                    "source_preview": "Article Dépannage serrurier : quelle prise en charge par votre assurance habitation et quels services pour déclarer votre sinistre rapidement.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "assurance habitation" in draft["subject"].lower()


def test_stage_two_rewrite_drafts_prefers_specific_credit_topic_over_generic_financing() -> (
    None
):
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-credit-specific-a",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "promotional_spam",
                    "rewrite_mode": "promotional_page_to_spam_message",
                    "target_label": "spam",
                    "raw_record_id": "credit-specific-a",
                    "source_preview": "Accès à vos comptes par l'écran de connexion pleine page Accéder au Menu Principal Accéder au Contenu éditorial Accéder au Pied de page Prêt relais Vous cherchez une solution pour préfinancer vos subventions, votre TVA ou une opération immobilière ou foncière.",
                },
                {
                    "job_id": "job-credit-specific-b",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "promotional_spam",
                    "rewrite_mode": "promotional_page_to_spam_message",
                    "target_label": "spam",
                    "raw_record_id": "credit-specific-b",
                    "source_preview": "Accès à vos comptes par l'écran de connexion pleine page Accéder au Menu Principal Accéder au Contenu éditorial Accéder au Pied de page Crédit Renouvelable Le Crédit Renouvelable de La Banque Postale est une solution de financement souple et flexible.",
                },
            ]
        }
    )

    first, second = drafts["drafts"]
    assert first["review_state"] == "usable"
    assert second["review_state"] == "usable"
    assert "prêt relais" in first["subject"].lower()
    assert "crédit renouvelable" in second["subject"].lower()
    assert first["text_sha256"] != second["text_sha256"]


def test_stage_two_rewrite_drafts_extracts_specific_assurance_offer_topic() -> None:
    drafts = StageTwoRewriteDraftService.build_drafts(
        {
            "jobs": [
                {
                    "job_id": "job-assurance-specific",
                    "source_name": "common-crawl-bigdata",
                    "rule_key": "promotional_spam",
                    "rewrite_mode": "promotional_page_to_spam_message",
                    "target_label": "spam",
                    "raw_record_id": "assurance-specific",
                    "source_preview": "LCL enrichit son offre d’assurance pour les NVEI Accéder aux autres espaces Particulier Banque privée Professionnel Entreprise Etudiant Journaliste Nous contacter Devenir client Mon espace METIERS Découvrez nos métiers LCL vous propose des produits et services.",
                }
            ]
        }
    )

    draft = drafts["drafts"][0]
    assert draft["review_state"] == "usable"
    assert "nvei" in draft["subject"].lower()


def test_stage_two_rewrite_drafts_render_markdown() -> None:
    markdown = StageTwoRewriteDraftService.render_markdown(
        {
            "generated_at": "2026-04-07T00:00:00+00:00",
            "draft_count": 1,
            "review_summary": {"usable": 1},
            "target_label_summary": {"legitimate": 1},
            "drafts": [
                {
                    "draft_id": "draft-1",
                    "job_id": "job-1",
                    "source_name": "common-crawl-bigdata",
                    "rewrite_mode": "institutional_page_to_notification",
                    "target_label": "legitimate",
                    "review_state": "usable",
                    "review_notes": [],
                    "quality_signals": {"french_marker_count": 4},
                    "subject": "Sujet",
                    "body": "Bonjour",
                }
            ],
        }
    )

    assert "# Stage-Two Rewrite Drafts" in markdown
    assert "draft-1" in markdown
    assert "Review summary" in markdown

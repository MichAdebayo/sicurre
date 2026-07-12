from __future__ import annotations

from data_platform.services.common_crawl.stage_two import CommonCrawlStageTwoService


def test_common_crawl_stage_two_accepts_transactional_legitimate() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Accéder au Menu Principal Réinitialiser votre mot de passe. "
            "Veuillez renseigner le formulaire ci-dessous. "
            "Vous recevrez votre mot de passe provisoire par SMS."
        ),
        {"category": "legitimate"},
    )

    assert result.route_outcome == "accepted"
    assert result.route_subtype == "transactional_legitimate"
    assert result.derived_payload is not None
    assert result.derived_payload["promotion_eligible"] is True


def test_common_crawl_stage_two_marks_promotional_spam_candidate() -> None:
    result = CommonCrawlStageTwoService.review(
        "Bonjour, profitez de notre offre exclusive avec réduction immédiate et code promo newsletter.",
        {"category": "spam_like", "query": "newsletter"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_promotional_candidate"
    assert result.route_subtype == "promotional_spam"
    assert result.derived_payload is not None
    assert result.derived_payload["candidate_subtype"] == "promotional_spam"


def test_common_crawl_stage_two_accepts_nested_transactional_window() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Accéder au Menu Principal Accéder au Contenu éditorial Réinitialiser votre mot de passe "
            "Nous vous aidons à récupérer votre mot de passe en cas de perte, vol, oubli ou à sécuriser l'accès à votre espace client internet. "
            "Choisissez l'envoi du mot de passe provisoire par SMS. Vous recevrez ensuite un code à usage unique sur votre numéro de téléphone mobile. "
            "Accéder au Pied de page"
        ),
        {"category": "legitimate"},
    )

    assert result.route_outcome == "accepted"
    assert result.route_subtype == "transactional_legitimate"
    assert "mot de passe provisoire" in result.extracted_text


def test_common_crawl_stage_two_demotes_product_page_with_delivery_signals() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Un accès à la gestion des comptes via votre Espace Client Internet Pour 1€/mois Découvrir la formule de compte. "
            "L'alerte SMS vous informe automatiquement de la situation de vos comptes et vous recevrez une notification sur votre messagerie personnelle."
        ),
        {"category": "legitimate"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_instructional_candidate"
    assert result.route_subtype == "instructional_legitimate"


def test_common_crawl_stage_two_recovers_weak_notification_window() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Selon les conditions générales d'Apple Pay et de Samsung Pay. "
            "Des virements par SMS ! Je rembourse mes amis instantanément par SMS, plus de RIB à mémoriser. "
            "Des notifications paramétrables vous informent automatiquement des mouvements sur votre compte."
        ),
        {"category": "legitimate"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_instructional_candidate"
    assert result.route_subtype == "instructional_legitimate"
    assert "notifications paramétrables" in result.extracted_text


def test_common_crawl_stage_two_recovers_product_offer_page_for_spam_adaptation() -> (
    None
):
    result = CommonCrawlStageTwoService.review(
        (
            "Accéder au Menu Principal Accéder au Contenu éditorial Accéder au Pied de page "
            "Article Petits budgets : trouvez une assurance habitation pas chère. "
            "Comparez les tarifs pour protéger votre logement avec une formule adaptée à votre budget."
        ),
        {"category": "legitimate"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_product_offer_candidate"
    assert result.route_subtype == "promotional_spam"


def test_common_crawl_stage_two_routes_signal_arnaques_pages_to_phishing_lane() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Ensemble contre les Arnaques Signaler une Arnaque Alertes du moment "
            "Distribution-retard.com Site internet frauduleux Page miroir mondial Relay. "
            "Aucun livreur n'est passé pendant cette plage horaire. "
            "Autre arnaque Message reçu ce jour. Escroquerie au faux colis."
        ),
        {
            "category": "phishing_related",
            "query": "signal-arnaques.com/*",
            "query_label": "scam_reports_fr",
            "url": "https://www.signal-arnaques.com/",
        },
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_phishing_lure_candidate"
    assert result.route_subtype == "phishing_lure_candidate"
    assert result.derived_payload is not None
    assert result.derived_payload["phishing_relevance"] is True


def test_common_crawl_stage_two_recovers_service_contact_holdout() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Tous les champs sont obligatoires. Contactez votre service client depuis la messagerie sécurisée. "
            "Une notification dédiée vous guidera ensuite dans votre espace habituel."
        ),
        {"category": "legitimate", "query_label": "bank_fr"},
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_account_recovery_candidate"
    assert result.route_subtype == "instructional_legitimate"


def test_common_crawl_stage_two_routes_cybermalveillance_pages_to_awareness() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Assistance aux victimes de cybermalveillance. Cybermalveillance.gouv.fr a pour missions "
            "de sensibiliser au risque cyber, d'informer sur les menaces numériques et les moyens de s'en protéger."
        ),
        {
            "category": "phishing_related",
            "query": "cybermalveillance.gouv.fr/*",
            "query_label": "cert_gov_fr",
            "url": "https://www.cybermalveillance.gouv.fr/",
        },
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_phishing_awareness_content"
    assert result.route_subtype == "awareness_or_report"


def test_common_crawl_stage_two_routes_cybermalveillance_awareness_without_phishing_category() -> (
    None
):
    result = CommonCrawlStageTwoService.review(
        (
            "Assistance aux victimes de cybermalveillance. Que faire en cas de phishing ou hameçonnage ? "
            "Comment se protéger contre une tentative de phishing et que faire si on en est victime ?"
        ),
        {
            "category": "legitimate",
            "query": "cybermalveillance.gouv.fr/*",
            "query_label": "cert_gov_fr",
            "url": "https://www.cybermalveillance.gouv.fr/tous-nos-contenus/fiches-reflexes/hameconnage-phishing",
        },
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_phishing_awareness_content"
    assert result.route_subtype == "awareness_or_report"


def test_common_crawl_stage_two_recovers_bank_faq_help_page() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Comment puis-je consulter mes plafonds de paiement et de retrait ? "
            "Vous pouvez consulter vos plafonds de paiement et de retrait depuis votre Espace Client. "
            "Connectez-vous à votre espace client et accédez au détail de votre carte pour consulter ces informations."
        ),
        {
            "category": "legitimate",
            "query": "www.labanquepostale.fr/*",
            "query_label": "bank_fr",
            "url": "https://www.labanquepostale.fr/particulier/faq-centre-aide/comptes-et-cartes/comptes-bancaires.question.html/comment-puis-je-consulter-mes-plafonds-de-paiement-et-de-retrait.html",
        },
    )

    assert result.route_outcome == "specialized_processing"
    assert result.route_reason == "common_crawl_faq_candidate"
    assert result.route_subtype == "instructional_legitimate"


def test_common_crawl_stage_two_keeps_signal_spam_barometer_out_of_awareness() -> None:
    result = CommonCrawlStageTwoService.review(
        (
            "Baromètre de la perception du spam pour le deuxième trimestre 2019. "
            "Téléchargez le baromètre et consultez les anciens baromètres."
        ),
        {
            "category": "phishing_related",
            "query": "signal-spam.fr/*",
            "query_label": "signal_spam_fr",
            "url": "https://www.signal-spam.fr/barometre-du-spam/",
        },
    )

    assert result.route_subtype != "awareness_or_report"

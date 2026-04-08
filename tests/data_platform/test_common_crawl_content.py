from __future__ import annotations

from data_platform.services.common_crawl_content import CommonCrawlContentService


def test_common_crawl_content_service_extracts_message_from_noisy_text() -> None:
    cleaned = CommonCrawlContentService.clean_web_text(
        (
            "Accéder au Menu Principal Accéder au Contenu éditorial Comment me protéger des risques de vol ? "
            "Réinitialiser votre mot de passe. Choisissez l'envoi du mot de passe provisoire par SMS. "
            "Vous recevrez un code à usage unique sur votre numéro de téléphone mobile. Accéder au Pied de page"
        )
    )

    assert "mot de passe provisoire" in cleaned
    assert "code à usage unique" in cleaned
    assert "Accéder au Menu Principal" not in cleaned


def test_common_crawl_content_service_extracts_text_from_html_prefers_message_blocks() -> (
    None
):
    cleaned = CommonCrawlContentService.extract_text_from_html(
        """
        <html>
          <body>
            <header>Accéder au Menu Principal</header>
            <main>
              <section>
                <p>Réinitialiser votre mot de passe.</p>
                <p>Vous recevrez un mot de passe provisoire par SMS puis un code à usage unique.</p>
              </section>
            </main>
            <footer>Contactez-nous</footer>
          </body>
        </html>
        """
    )

    assert "mot de passe provisoire" in cleaned
    assert "Accéder au Menu Principal" not in cleaned


def test_common_crawl_content_service_prioritizes_message_like_urls() -> None:
    strong_score = CommonCrawlContentService.score_url(
        "https://www.labanquepostale.fr/particulier/securite/reinitialiser-mot-de-passe.html",
        "legitimate",
    )
    weak_score = CommonCrawlContentService.score_url(
        "https://www.labanquepostale.fr/article/interview-banque-au-service-de-tous.html",
        "legitimate",
    )

    assert strong_score > weak_score

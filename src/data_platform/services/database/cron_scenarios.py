from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CronArchetypeScenario:
    scenario_id: str
    class_name: str
    archetype_id: str
    family: str


CRON_ARCHETYPE_SCENARIOS: tuple[CronArchetypeScenario, ...] = (
    CronArchetypeScenario(
        scenario_id="phishing_messaging_prompt",
        class_name="phishing",
        archetype_id="p_simple_whatsapp",
        family="messaging",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_investment_pitch",
        class_name="phishing",
        archetype_id="p_medium_investissement",
        family="investment",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_cloud_billing_lockout",
        class_name="phishing",
        archetype_id="p_medium_icloud",
        family="cloud_account",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_health_reimbursement",
        class_name="phishing",
        archetype_id="p_medium_ameli",
        family="healthcare",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_tax_refund_notice",
        class_name="phishing",
        archetype_id="p_medium_impots",
        family="tax",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_delivery_fee_hold",
        class_name="phishing",
        archetype_id="p_medium_laposte",
        family="parcel",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_bank_security_review",
        class_name="phishing",
        archetype_id="p_medium_banque",
        family="banking",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_document_share_lure",
        class_name="phishing",
        archetype_id="p_hard_onedrive",
        family="document_share",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_urssaf_deadline",
        class_name="phishing",
        archetype_id="p_hard_urssaf",
        family="urssaf",
    ),
    CronArchetypeScenario(
        scenario_id="phishing_bec_supplier_change",
        class_name="phishing",
        archetype_id="p_hard_bec",
        family="business_email_compromise",
    ),
    CronArchetypeScenario(
        scenario_id="spam_casino_bonus",
        class_name="spam",
        archetype_id="s_simple_casino",
        family="gambling",
    ),
    CronArchetypeScenario(
        scenario_id="spam_dating_match",
        class_name="spam",
        archetype_id="s_simple_rencontre",
        family="dating",
    ),
    CronArchetypeScenario(
        scenario_id="spam_supplement_flash_sale",
        class_name="spam",
        archetype_id="s_simple_pharmacie",
        family="supplements",
    ),
    CronArchetypeScenario(
        scenario_id="spam_survey_voucher",
        class_name="spam",
        archetype_id="s_simple_loterie_pub",
        family="survey_offer",
    ),
    CronArchetypeScenario(
        scenario_id="spam_ecommerce_flash_sale",
        class_name="spam",
        archetype_id="s_medium_ecommerce",
        family="retail_marketing",
    ),
    CronArchetypeScenario(
        scenario_id="spam_seo_outreach",
        class_name="spam",
        archetype_id="s_medium_seo",
        family="seo_outreach",
    ),
    CronArchetypeScenario(
        scenario_id="spam_predatory_journal",
        class_name="spam",
        archetype_id="s_medium_journal_academique",
        family="academic_spam",
    ),
    CronArchetypeScenario(
        scenario_id="spam_b2b_pitch",
        class_name="spam",
        archetype_id="s_medium_b2b_prospection",
        family="b2b_prospecting",
    ),
    CronArchetypeScenario(
        scenario_id="spam_tech_newsletter",
        class_name="spam",
        archetype_id="s_hard_newsletter_tech",
        family="newsletter",
    ),
    CronArchetypeScenario(
        scenario_id="spam_webinar_registration",
        class_name="spam",
        archetype_id="s_hard_webinaire",
        family="webinar",
    ),
    CronArchetypeScenario(
        scenario_id="legit_order_confirmation",
        class_name="legitimate",
        archetype_id="l_simple_confirmation_commande",
        family="order",
    ),
    CronArchetypeScenario(
        scenario_id="legit_delivery_update",
        class_name="legitimate",
        archetype_id="l_simple_expedition",
        family="delivery",
    ),
    CronArchetypeScenario(
        scenario_id="legit_support_acknowledgement",
        class_name="legitimate",
        archetype_id="l_simple_accuse_reception",
        family="support",
    ),
    CronArchetypeScenario(
        scenario_id="legit_saas_newsletter",
        class_name="legitimate",
        archetype_id="l_medium_newsletter_saas",
        family="saas",
    ),
    CronArchetypeScenario(
        scenario_id="legit_invoice_receipt",
        class_name="legitimate",
        archetype_id="l_medium_facture_legitime",
        family="billing",
    ),
    CronArchetypeScenario(
        scenario_id="legit_professional_meeting",
        class_name="legitimate",
        archetype_id="l_medium_convocation",
        family="professional_notice",
    ),
    CronArchetypeScenario(
        scenario_id="legit_france_travail_notice",
        class_name="legitimate",
        archetype_id="l_medium_france_travail",
        family="public_service",
    ),
    CronArchetypeScenario(
        scenario_id="legit_bank_activity_notice",
        class_name="legitimate",
        archetype_id="l_hard_notification_bancaire",
        family="banking",
    ),
    CronArchetypeScenario(
        scenario_id="legit_urssaf_reminder",
        class_name="legitimate",
        archetype_id="l_hard_urssaf_reel",
        family="urssaf",
    ),
    CronArchetypeScenario(
        scenario_id="legit_security_alert",
        class_name="legitimate",
        archetype_id="l_hard_alerte_securite_reelle",
        family="security",
    ),
)


CRON_ARCHETYPE_SCENARIOS_BY_CLASS: dict[str, tuple[CronArchetypeScenario, ...]] = {
    class_name: tuple(
        scenario
        for scenario in CRON_ARCHETYPE_SCENARIOS
        if scenario.class_name == class_name
    )
    for class_name in ("phishing", "spam", "legitimate")
}

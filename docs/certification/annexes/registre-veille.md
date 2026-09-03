# Registre de veille technique et réglementaire

## Organisation

- **Périmètre** : IA francophone, sécurité API, sécurité des données, routage
  e-mail et accessibilité des livrables.
- **Cadence prévue** : une heure chaque semaine ; revue immédiate lors d'une
  alerte CERT-FR/ANSSI ou d'un changement de fournisseur critique.
- **Agrégation** : flux RSS officiels lorsqu'ils existent, notifications de
  versions GitHub et favoris documentaires ; aucune source sociale anonyme ne
  suffit à valider une décision.
- **Partage** : synthèse Markdown accessible dans le dépôt, puis export PDF
  balisé pour la remise. Titres structurés, liens explicites et tableaux avec
  en-têtes permettent une lecture clavier ou par lecteur d'écran.
- **Fiabilité** : priorité aux organismes publics, documentation éditeur et
  publications scientifiques identifiant leurs auteurs. Une information
  commerciale est recoupée avant de devenir une décision.

## Relevé du 17 juillet 2026

| Thème | Source primaire et auteur | Date/actualité | Fiabilité | Synthèse utile | Décision Sicurre |
|---|---|---|---|---|---|
| Modèle français | Antoun et al., [CamemBERT 2.0](https://arxiv.org/abs/2411.08868) | publication 2024, consultée le 17/07/2026 | Haute : auteurs identifiés, article scientifique et artefacts ouverts | CamemBERTav2 repose sur DeBERTaV3/RTD, un corpus français plus récent et un tokenizer actualisé | Conserver CamemBERTav2 comme encodeur spécialisé ; versionner révision et dataset |
| API et abus de ressources | OWASP Foundation, [API4:2023](https://owasp.org/API-Security/editions/2023/en/0xa4-unrestricted-resource-consumption/) | édition 2023, consultée le 17/07/2026 | Haute : référentiel communautaire reconnu, auteur institutionnel | Recommande limites de débit, tailles, temps et consommation fournisseur | Rate limits par route, pagination bornée, timeouts et budgets externes |
| Données personnelles | CNIL, [Guide sécurité des données](https://www.cnil.fr/fr/guide-de-la-securite-des-donnees-personnelles-nouvelle-edition-2024) | 26/03/2024, consulté le 17/07/2026 | Haute : autorité française de contrôle | Ajoute des recommandations spécifiques aux systèmes d'IA et rappelle l'obligation de sécurité | Minimisation, chiffrement, séparation locataire et absence de contenu brut par défaut |
| Routage e-mail | Cloudflare, [Email Routing rules](https://developers.cloudflare.com/email-service/configuration/email-routing-addresses/) | mise à jour 09/06/2026, consultée le 17/07/2026 | Haute pour le comportement produit : documentation éditeur datée | Une règle associe une adresse à une destination vérifiée ou un Worker ; les destinations sont partagées au niveau compte | Worker par domaine et destination vérifiée ; provisionnement idempotent et erreurs de permission explicites |
| Service managé alternatif | Hugging Face, [Inference Endpoints Security](https://huggingface.co/docs/inference-endpoints/security) et [Pricing](https://huggingface.co/docs/inference-endpoints/pricing) | consulté le 17/07/2026 | Moyenne-haute : documentation éditeur, intérêt commercial explicite | TLS, endpoints protégés/privés, logs annoncés 30 jours ; facturation à la minute selon l'instance | Alternative viable mais non retenue pour le POC : coût, rétention déclarée et dépendance fournisseur |
| API générative alternative | OpenAI, [Enterprise privacy](https://openai.com/enterprise-privacy/) et [Data controls](https://platform.openai.com/docs/models/default-usage-policies-by-endpoint) | mise à jour 08/01/2026, consultée le 17/07/2026 | Moyenne-haute : documentation fournisseur ; conditions à vérifier contractuellement | Données API non utilisées pour l'entraînement par défaut ; conservation de surveillance pouvant atteindre 30 jours sauf contrôles éligibles | Ne pas envoyer les e-mails par défaut ; LLM optionnel seulement après analyse de traitement et consentement/configuration appropriée |

## Synthèse communiquable

La veille confirme le choix d'un classifieur français auto-hébergé pour limiter
le transfert de contenu et maîtriser la version du modèle. Elle ne permet pas de
revendiquer automatiquement une conformité RGPD : cette conformité dépend des
finalités, durées, mesures de sécurité et contrats réellement appliqués. Les
services managés restent des alternatives à mesurer ; leurs garanties éditeur
ne remplacent ni le benchmark Sicurre ni l'analyse de risques.

## Prochaine revue

À la prochaine séance, enregistrer : évolution CERT-FR des campagnes phishing,
modification éventuelle des API Cloudflare Email Service, avis CNIL/EDPB relatif
aux systèmes d'IA et notes de version du modèle/runtime ONNX. Chaque nouvelle
entrée doit indiquer son impact ou la décision « aucun changement ».

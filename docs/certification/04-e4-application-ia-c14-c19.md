# E4 — Conception et réalisation de l'application Sicurre

## Périmètre de l'évaluation

Ce rapport couvre les compétences **C14 à C19** du Bloc 4 de la certification pour le système Sicurre. Il présente l'analyse des besoins utilisateurs, le cadre technique de l'application Web SaaS, la méthodologie de coordination du développement, l'implémentation des composants interactifs, les stratégies de tests automatisés d'interface et la procédure globale de déploiement en production.

---

## 1. C14 — Analyser le besoin

### 1.1 Commanditaire et cibles utilisateurs
- **Commanditaire** : Projet initié par Simplon pour évaluer la mise en production de solutions d'IA appliquées.
- **Utilisateurs cibles** : Auto-entrepreneurs, artisans et dirigeants de Très Petites Entreprises (TPE) français.
- **Contraintes utilisateurs** : Absence de support informatique dédié, budget restreint, besoin d'une solution autonome et transparente s'intégrant sans modifier leurs clients de messagerie existants.
- **Scénario pilote Vinse** : le domaine réel de démonstration `vinse.app` sert à valider une activation sans changement de client de messagerie et la correction des faux positifs/négatifs.

### 1.2 Parcours utilisateur (User Journey)
Le parcours est conçu pour minimiser la charge cognitive :
1. **Inscription / Connexion** : Création de compte sécurisée via Better Auth.
2. **Onboarding Cloudflare** : Saisie sécurisée du jeton API Cloudflare. L'application configure automatiquement la redirection DNS (MX records) et déploie le worker d'interception d'e-mails.
3. **Tableau de bord de sécurité** : Consultation des indicateurs clés (volume traité, spams interceptés, phishing neutralisé).
4. **Quarantaine et historique** : Visualisation des messages interceptés avec possibilité de libérer un e-mail légitime ("restaurer dans la boîte de réception") ou de signaler un message suspect non détecté.
5. **Déconnexion** : Révocation instantanée de la session de navigation.

### 1.3 Objectif d'accessibilité (WCAG AA) et thèmes
L'interface vise WCAG 2.2 AA grâce aux jetons sémantiques, aux labels, aux états
de focus et aux thèmes clair/sombre. Cette cible n'est pas encore une conformité
prouvée sur toutes les routes : l'audit automatisé et manuel, clavier compris,
reste à joindre avant de marquer C14 validé.

---

## 2. C15 — Concevoir le cadre technique

L'architecture applicative est découpée en couches autonomes communicant par des canaux sécurisés :

- **React & TypeScript (Frontend)** : Fournit l'interface utilisateur dynamique de production, exploitant les composants d'interface standardisés et le système de routage client.
- **Better Auth (Authentication)** : Module d'authentification s'exécutant dans un processus conteneurisé dédié pour gérer les sessions de navigation, l'enregistrement des utilisateurs et l'authentification forte sans stocker de secrets applicatifs dans le code client.
- **FastAPI Gateway (Backend API)** : Seul point d'entrée vers la base de données PostgreSQL Neon. Gère l'authentification des requêtes, le chiffrement AES-256-GCM des jetons Cloudflare utilisateurs, et délègue les classifications au conteneur ML.
- **Cloudflare Email Worker** : Code JavaScript s'exécutant sur le réseau Edge de Cloudflare pour intercepter, inspecter et réacheminer les flux d'e-mails entrants.
- **Grafana Alloy** : Agent de collecte de télémétrie locale qui agrège les logs de conteneurs, les traces applicatives et les métriques de performance système.

### 2.1 Application des recommandations OWASP Top 10

Les recommandations sont appliquées selon les risques réellement exposés par
Sicurre, et non comme une simple liste déclarative :

| Risque OWASP | Contrôle Sicurre et preuve |
|---|---|
| A01 Contrôle d'accès défaillant | Authentification centrale, rôles opérateur et filtrage systématique par `workspace_id` ; tests IDOR de toutes les ressources locataire dans `test_tenant_isolation.py`. |
| A02 Défaillances cryptographiques | TLS 1.2/1.3 à l'entrée, mots de passe hachés par Better Auth, secrets fournisseurs chiffrés par AES-256-GCM et clé obligatoire en production. |
| A03 Injection | Requêtes paramétrées SQLAlchemy/SQL, identifiants et pagination validés par Pydantic, commandes POC sur liste fermée sans interpolation shell. |
| A04 Conception non sécurisée | Séparation navigateur, sidecar d'authentification, API seule détentrice des accès DB, limites de taille/débit et comportement fail-closed pour l'inférence et les callbacks internes. |
| A05 Mauvaise configuration | Validation des variables de production, images non-root, ports origine liés au loopback, TLS et en-têtes `X-Frame-Options`, `X-Content-Type-Options` et `Referrer-Policy`. |
| A06 Composants vulnérables | `npm audit` et `pip-audit` bloquent les vulnérabilités élevées dans la CI ; images et dépendances sont séparées par runtime. |
| A07 Identification/authentification | Sessions Better Auth, origines de confiance, Turnstile à l'inscription, longueurs de mot de passe bornées et comparaison constante des clés internes. |
| A08 Intégrité logiciel/données | Images GHCR identifiées par SHA, datasets gelés avec checksum, provenance modèle liée et branches protégées avec CI obligatoire. |
| A09 Journalisation/surveillance | Logs structurés sans contenu brut, métriques et traces Alloy/Grafana, santé de service et tableaux de bord séparés ; les alertes opérateur restent à joindre comme preuve C20. |
| A10 SSRF | Les destinations de services sortants viennent de la configuration serveur ; les URI de quarantaine sont bornées au stockage et au locataire, avec tests de rejet des chemins étrangers ou échappés. |

Cette couverture permet de considérer l'implémentation OWASP attendue comme
réalisée. Une capture des en-têtes de production et un scan DAST authentifié
restent des preuves complémentaires recommandées, sans remplacer les tests de
contrôle d'accès et de contrat déjà automatisés.

---

## 3. C16 — Coordonner la réalisation

L'équipe projet Sicurre utilise une méthodologie de développement collaborative stricte :
- **Gestion des branches** : Les développeurs travaillent sur des branches de fonctionnalités isolées (ex. `feature/tenant-isolation`).
- **Pull Requests** : les règles de dépôt imposent une PR et les contrôles requis vers `develop`, puis de `develop` vers `main`. Le dossier final doit joindre une PR réellement passée au vert ; il ne doit pas inventer une revue par un second membre.
- **Promotion de production** : Le passage de la branche `develop` à la branche stable `main` fait l'objet d'une validation finale après tests d'intégration en préproduction (Staging smoke tests).

---

## 4. C17 — Développer les composants

### 4.1 POC Streamlit de validation
Pour valider l'ergonomie et la faisabilité technique du parcours de messagerie avant le développement complet de l'interface React, un POC fonctionnel a été implémenté en Streamlit sous [src/poc/](../../src/poc/).
- **Modularisation** : Extraction des styles et de la logique métier pour réduire la taille du fichier central `app.py` de ~2500 à 313 lignes, déléguant les rendus et calculs à des modules purs typés.
- **Gestion de thèmes** : Le module [theme_overrides.py](../../src/poc/presentation/theme_overrides.py) injecte dynamiquement des règles CSS basées sur le choix de thème Streamlit (`light` ou `dark`), modifiant en profondeur l'apparence des composants natifs pour respecter la charte graphique Sicurre.
- **Hiérarchie chromatique** : le bleu primaire identifie les contrôles, le focus
  et les états sélectionnés. L'ambre est réservé aux avertissements et le rouge
  aux verdicts phishing. Les chevrons de repli, contrôles segmentés, listes et
  cases à cocher possèdent des états survol/focus contrastés dans les deux thèmes.
- **Filiation lisible** : le graphique regroupe les volumes par famille parent
  d'acquisition (fichier, base de données, Big Data, scraping, API) et conserve
  une couleur distincte par famille. Pour la base V1 reconstruite, les totaux
  proviennent de `source_distribution` dans les métadonnées de l'artefact figé ;
  les collectes postérieures utilisent leur lignée réelle en base. Cette méthode
  conserve exactement le total de 32 288 lignes sans prétendre disposer d'une
  provenance par enregistrement que la reconstruction n'a pas conservée.

### 4.2 Opérations de démonstration protégées

| Action POC | Effet réel | Protection |
|---|---|---|
| Reconstruire la base | Rejoue la base figée dans le SQLite POC | Refuse toute URL non SQLite ; ne touche pas Neon |
| Exemple de cron incrémental | Exécute uniquement le collecteur SEKOIA et écrit dans SQLite et sous `data/local/poc/snapshots/demonstrations/poc/...` | Aucun commutateur ne permet une écriture R2 ou production depuis ce parcours |
| Normaliser + construire | Normalise et construit un aperçu local uniquement si les éléments éligibles diffèrent de la dernière version | Aucune version identique, publication Kaggle ou dispatch Sicurre-ML |

Les commandes sont une liste fermée d'arguments, la sortie est bornée et
expurgée, et aucun texte saisi dans l'interface ne devient une commande shell.
SEKOIA est volontairement l'exemple réel, court et reproductible du POC ; le
lot collecté reste un corpus d'indicateurs de référence. La vue « Jeux de
données » sépare donc le volume brut du nombre de messages normalisés et de la
contribution effective à la dernière version du dataset.
Le bouton ne prétend pas lancer l'orchestrateur complet. En production, chaque
source conserve sa cadence propre et le job mensuel agrège les deltas éligibles
avant le gel, la publication et le dispatch ML.

### 4.3 Restauration et Signalement (Feedback loop)
- **Faux Positif (Restauration)** : le bouton invoque une route asynchrone qui charge le MIME privé, valide que le destinataire connecté est une adresse Email Routing vérifiée, demande sa retransmission via Cloudflare Email Sending et enregistre la correction. Ce contrat exploite le chemin gratuit prévu par Cloudflare pour les destinations vérifiées ; il ne nécessite pas l'onboarding payant d'un domaine d'envoi et interdit les destinataires arbitraires. La preuve E2E contrôlée du 18 juillet 2026 a écrit un MIME synthétique dans R2, l'a délivré à l'adresse vérifiée avec l'identifiant Cloudflare `<identifiant-cloudflare-redige@vinse.app>`, persisté l'état `released` sans erreur, enregistré une seule correction `false_positive -> legitimate`, supprimé l'objet MIME de R2, puis confirmé qu'une seconde demande retournait `idempotent: true` sans nouvel envoi.
- **Faux Négatif (Signalement)** : crée un feedback tenant-scopé corrélé à l'événement lorsque disponible. Le contenu brut n'est pas ajouté automatiquement au corpus ; une revue opérateur/ML est nécessaire avant toute annotation ou réutilisation.

---

## 5. C18 — Automatiser les tests

Sicurre applique une pyramide des tests rigoureuse :

1. **Tests unitaires (Python/Pytest)** : 93 tests POC passent au contrôle local du 24 août 2026, avec 91% de couverture agrégée et 93% sur les nouveaux modules de ce passage ; les chiffres définitifs restent ceux de l'artefact CI du commit présenté.
2. **Tests d'intégration (API/Neon)** : Validation des transactions de base de données et de la conformité du contrat OpenAPI.
3. **Tests d'isolation de locataires (IDOR)** : Tests vérifiant qu'aucun identifiant de requête falsifié (manipulation de `workspace_id`) ne permet d'accéder aux données d'un autre utilisateur.
4. **Tests d'intégration d'Interface (AppTest)** : Simulation complète du comportement utilisateur dans le POC Streamlit (authentification, clic sur les boutons de remédiation, navigation) sans dépendre d'un navigateur externe.

---

## 6. C19 — Livrer l'application

Le déploiement applicatif est orchestré par Docker Compose et géré sur des serveurs Cloud virtuels souverains (Hetzner).

- **Images de conteneur** : construites et publiées sur GHCR avec un tag SHA immuable. Aucune signature cryptographique ne doit être revendiquée tant qu'une étape d'attestation/signature n'existe pas.
- **Reverse Proxy Partagé** : Nginx termine TLS avec le certificat d'origine
  installé sur l'hôte et route le trafic vers le gateway Sicurre lié uniquement
  à `127.0.0.1:8002`. Cloudflare protège l'entrée publique.
- **Smoke Tests** : Après recréation de la stack, le CD interroge jusqu'à trente
  fois `/__app/health` et `/health`. Un échec empêche le job de déploiement
  d'aboutir ; le workflow n'implémente pas de bascule blue/green.

### 6.1 Preuve de livraison du 17 juillet 2026

La production utilisait l'image immuable `v1.4.2`. Les services applicatifs
étaient sains, Nginx validait sa configuration, et les trois contrats loopback
retournaient HTTP 200. L'historique GitHub montrait une CI réussie sur `app`,
`develop`, puis `main`, suivie d'un CD réussi sur `main`. Les images antérieures
étaient encore présentes sur l'hôte.

### 6.2 Exercice de rollback du 18 juillet 2026

Une fenêtre contrôlée a ensuite validé le mécanisme de reprise opérateur. La
stack a été ramenée de `v1.4.2` à l'image immuable `v1.4.1`. La première sonde a
observé la courte fenêtre normale de redémarrage (`000`), puis la seconde a
retourné HTTP 200 pour le gateway, l'API et Better Auth. La version `v1.4.2` a
été restaurée et les trois surfaces ont de nouveau retourné HTTP 200. Cette
preuve démontre la réversibilité des images et la procédure ; elle ne constitue
pas un rollback automatique du workflow CD.

![Preuve du rollback contrôlé de production](screenshots/e5-controlled-production-rollback.png)

*Figure E4-1 — Rollback `v1.4.2 → v1.4.1`, contrôles de santé, puis restauration
de `v1.4.2`, le 18/07/2026. La figure ne contient ni secret ni donnée client.*

---

## 7. Accessibilité et UX : Tableau de conformité

| Composant | Règle d'accessibilité appliquée | Statut de validation |
|---|---|---|
| **Formulaire d'authentification** | Labels, autocomplete et focus à vérifier sur navigateur. | `À AUDITER` |
| **Console Settings & Cloudflare** | Instructions et erreurs contextualisées. | `PARTIEL` — test lecteur d'écran à joindre |
| **Graphiques** | Polices, légendes, contraste, état vide et réduction de mouvement. | `À AUDITER` |
| **Sélection de thème** | Persistance, focus, contraste clair/sombre. | `PARTIEL` — parcours clavier à joindre |

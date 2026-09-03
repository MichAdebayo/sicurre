# E5 — Monitorage et résolution d'un incident technique

## Périmètre de l'évaluation

Ce livrable couvre l'épreuve **E5** et les compétences **C20 et C21** du Bloc 3 de la certification pour le système Sicurre. Il décrit l'architecture d'observabilité mise en production pour surveiller l'application et l'infrastructure, détaille le scénario d'incident d'indisponibilité de l'IA (reproduction, impact, diagnostic et correction) et recense les preuves de débogage pour quatre autres incidents techniques réels survenus durant le cycle de vie du projet.

---

## 1. C20 — Surveiller l'application (Observabilité)

Sicurre implémente une architecture de surveillance télémétrique moderne, souveraine et hautement optimisée pour respecter les limites budgétaires de l'hébergement gratuit Grafana Cloud.

### 1.1 Architecture d'observabilité technique
- **Instrumentation Sicurre** : l'API FastAPI émet des traces OTLP avec un échantillonnage en tête configurable. Les métriques du gateway, de l'hôte, des conteneurs et d'Alloy sont collectées par Prometheus. L'instrumentation du modèle est prouvée séparément dans Sicurre-ML.
- **Collecteur Grafana Alloy** : Un agent Alloy léger (`v1.16.1`) s'exécute localement sur chaque machine pour découvrir dynamiquement les conteneurs Docker, collecter leurs métriques système, lire leurs logs et les acheminer vers les backends Grafana Cloud (Prometheus pour les métriques, Loki pour les logs, Tempo pour les traces).
- **Consoles de supervision (Dashboards)** : Trois tableaux de bord Grafana distincts permettent d'inspecter séparément :
  1. **Dashboard Applicatif** : disponibilité du gateway, débit des requêtes, latence p95 globale et par surface (`app`, `api`, `auth`), résultats HTTP et erreurs de proxy. Il ne présente pas encore de métriques métier de quarantaine ou de remédiation.
  2. **Dashboard Infrastructure** : Utilisation du processeur CPU, mémoire RAM par conteneur et débit réseau.
  3. **Dashboard Télémétrique** : disponibilité et durée des scrapes, nombre d'échantillons collectés, consommation d'Alloy et état des écritures distantes Prometheus. Le taux d'échantillonnage des traces n'est pas exposé dans ce dashboard.

### 1.2 Gestion du budget télémétrique (Free Tier Alignment)
Pour éviter tout dépassement des quotas d'exposition de Grafana Cloud, plusieurs filtres d'optimisation sont appliqués au niveau de la configuration Alloy :
- **Fréquence de scrape** : les quatre cibles Sicurre sont configurées à 60 secondes.
- **Filtrage des labels Loki** : Retrait automatique de tous les labels dynamiques à haute cardinalité (tels que les identifiants d'événements, identifiants d'e-mails ou adresses IP clients) pour prévenir l'explosion des index Loki.
- **Traces** : l'API applique `ParentBased(TraceIdRatioBased(...))`, donc un échantillonnage en tête par ratio. Aucun tail sampling erreur/latence n'est implémenté dans Alloy ; il ne doit pas être revendiqué.
- **Sondes de santé silencieuses** : Les requêtes régulières des sondes de santé de l'orchestrateur (Health Check probes) sur `/health` sont filtrées à la source pour éviter de polluer Loki avec des messages de logs répétitifs sans valeur métier.

### 1.3 Seuil d'alertes opérationnelles

| Nature de l'incident | Métrique surveillée | Seuil d'alerte | Action déclenchée |
|---|---|---|---|
| **Service d'inférence hors-ligne** | métrique de disponibilité Sicurre-ML | `< 1` pendant 2 minutes | Règle à provisionner et tester |
| **Erreurs HTTP critiques** | taux de réponses `5xx` | `> 2%` sur 5 minutes | Règle à provisionner et tester |
| **Dégradation des performances** | p95 mesuré | dépassement du SLO sur 5 minutes | Règle à provisionner et tester |
| **Indisponibilité du collecteur** | `up` de la cible Alloy | `0` pendant 2 minutes | Règle à provisionner et tester |

Ces seuils sont les objectifs initiaux. Le dépôt contient les dashboards, mais pas
encore les règles d'alerte/contact Grafana codifiées ; C20 reste partiel tant
qu'une alerte de test n'a pas été reçue et capturée.

### 1.4 Protection des données personnelles (Privacy by Design)
Les métriques ne doivent porter aucun label utilisateur/message et les corps ne
doivent pas être journalisés. Les routes de santé, documentation et métriques
sont exclues des traces automatiques. Aucun filtre OTel générique de masquage des
exceptions n'est actuellement implémenté : la preuve finale doit donc combiner
revue des logs émis, tests de non-divulgation et, si nécessaire, sanitisation à la
source avant de déclarer la protection PII complète.

### 1.5 Validation externe datée

Le 17 juillet 2026, une vérification en lecture seule a confirmé les éléments
suivants sur l'environnement Hetzner et Grafana Cloud :

- les six services Sicurre étaient démarrés et les services munis d'une sonde
  Compose étaient sains ; aucun événement `error`, `exception`, `traceback` ou
  `fatal` n'était présent dans les journaux des quatre services applicatifs sur
  la fenêtre des trente dernières minutes ;
- les contrats loopback du gateway, de l'API et de Better Auth répondaient en
  HTTP 200 et la configuration Nginx passait `nginx -t` ;
- les endpoints Prometheus du gateway, de node-exporter et de cAdvisor
  répondaient en HTTP 200 avec des payloads métriques non vides ;
- l'API de lecture Prometheus de Grafana retournait quatre séries
  `up{stack="sicurre"}` à la valeur `1` : application, hôte, conteneurs et Alloy ;
- les trois dashboards versionnés Sicurre étaient présents dans Grafana.
- Loki retournait sept streams sur vingt-quatre heures couvrant Alloy, Better
  Auth, l'API et le gateway ; Tempo retournait deux traces récentes. Une fenêtre
  courte peut légitimement ne contenir aucun log applicatif lorsque le trafic est
  nul, car les accès et sondes routiniers sont volontairement supprimés.

Cette preuve confirme les chaînes métriques, logs et traces. Elle ne remplace pas
la capture d'une alerte réelle ni les figures visuelles demandées dans le dossier
final.

### 1.6 Captures Drilldown disponibles

Les captures sont conservées par surface afin d'éviter un écran unique illisible.
Elles prouvent la séparation des namespaces, mais elles documentent aussi les
défauts observés : une capture d'erreur n'est pas présentée comme un état sain.

![Journaux Sicurre API](screenshots/Drilldown%20logs/sicurre%20api.png)

*Figure E5-1 — Stream `sicurre-api` dans Loki. La fenêtre montre notamment
l'incident du Bearer vide, utilisé pour remonter au contrat de configuration.*

![Journaux du service d'inférence ML](screenshots/Drilldown%20logs/sicurre%20ml%20inference.png)

*Figure E5-2 — Stream `sicurre-ml-inference`, séparé du namespace applicatif.
Les requêtes `/v1/metrics` en HTTP 400 révèlent un défaut de scrape ML encore à
corriger ; elles ne sont pas une preuve de disponibilité métrique.*

![Traces Sicurre et Sicurre-ML](screenshots/Drilldown%20traces/sicurre%20trace.png)

*Figure E5-3 — Drilldown Tempo sur 24 heures, avec services
`sicurre-api` et `sicurre-ml-inference`, taux de spans, erreurs et durées.*

Les autres captures de ce dossier couvrent le gateway, Better Auth et les deux
collecteurs Alloy. Pour la preuve métrique finale, trois vues suffisent :

1. disponibilité des cibles avec `up{stack=~"sicurre|sicurre-ml"}` ;
2. débit, taux 5xx et p95 du gateway avec les métriques
   `sicurre_app_gateway_*`, ventilées par `route` ;
3. CPU/mémoire hôte et état de remote-write depuis les dashboards Infrastructure
   et Telemetry. Une galerie des centaines de métriques n'ajouterait aucune
   preuve de compétence.

---

## 2. C21 — Incident principal : Inférence indisponible

### 2.1 Description de la panne
Le service d'inférence locale (Sicurre-ML) est arrêté, ou configuré avec des paramètres réseau erronés.
- **Impact utilisateur** : le POC refuse de fabriquer un résultat et affiche une erreur contextualisée. En production, le Worker livre en mode disponibilité avec `X-Sicurre-Scan-Status` indiquant l'échec ; le message n'est pas présenté comme scanné.
- **Reproduction contrôlée** : le POC Streamlit expose aux administrateurs une page « Résilience ». Son déclencheur exerce explicitement l'exception typée `PocInferenceUnavailable`, présente le symptôme, le diagnostic, la reprise et la validation, sans interrompre un conteneur ni persister une fausse classification.

### 2.2 Résolution technique
La résolution de cet incident dans le code s'articule autour des points suivants :
1. **Client HTTP robuste** : Implémentation de timeouts explicites via `httpx` pour éviter des attentes indéfinies qui bloqueraient les threads de l'API FastAPI.
2. **Traitement d'erreur contextualisé** : L'API FastAPI intercepte les exceptions `ConnectError` et `Timeout` issues du service ML et retourne un code d'erreur clair `HTTP 503 Service Unavailable` plutôt que de planter ou de renvoyer un code `500` indéterminé.
3. **Comportement d'interface robuste** : L'interface du client Streamlit intercepte le statut d'erreur et affiche un bandeau d'alerte d'indisponibilité contextualisé, expliquant à l'utilisateur que la classification locale est temporairement inaccessible. L'application empêche la soumission d'avis de feedback durant la panne pour ne pas polluer la base de données.

---

## 3. Incidents d'infrastructure supplémentaires résolus

Quatre incidents techniques réels survenus durant les phases de développement et de déploiement ont été documentés et résolus :

### 3.0 Contrat de secret d'inférence en production

Le message contrôlé `SICURRE-E2E-20260717-01` a été livré au destinataire mais
n'a pas atteint Sicurre-ML. La corrélation temporelle des journaux a identifié
`Illegal header value b'Bearer '`: le conteneur exposait
`SICURRE_INFERENCE_API_KEY`, tandis que la configuration Python ne lisait que
`INFERENCE_API_KEY`. Le Worker a appliqué le comportement fail-open prévu ;
aucun événement de menace n'a été fabriqué et aucun corps brut n'a été conservé.

La correction ajoute un alias typé et un test de régression. Après synchronisation
du secret, les empreintes des clés runtime app/ML correspondent et un appel
authentifié direct à `/v1/classify` retourne HTTP 200. Ce diagnostic prouve la
détection et la reprise technique, mais un nouvel e-mail à sujet unique reste
nécessaire pour valider la chaîne complète.

Runbook détaillé : [06-contrat-cle-inference-production.md](incidents/06-contrat-cle-inference-production.md).

### 3.1 Better Auth échoue sur un runner CI propre
- **Symptôme** : Les tests d'intégration JavaScript échouaient systématiquement sur GitHub Actions lors de l'initialisation du serveur Better Auth.
- **Cause** : Le constructeur tentait d'instancier une base SQLite dans un sous-dossier local inexistant sur le conteneur vierge de la CI.
- **Résolution** : Modification de la logique de démarrage pour différer la création du répertoire et mock du chemin de stockage lors des tests unitaires d'interface.
- **Runbook associé** : [02-better-auth-sqlite-runner.md](../../docs/certification/incidents/02-better-auth-sqlite-runner.md).

### 3.2 Provisionnement Cloudflare refusé (Permissions API)
- **Symptôme** : L'utilisateur tentait d'activer la protection de son domaine mais le processus échouait avec une erreur de permission.
- **Cause** : Le jeton API Cloudflare fourni par l'utilisateur ne disposait pas des permissions d'écriture indispensables sur les zones DNS et les configurations d'Email Routing.
- **Résolution** : le provisionneur ne masque plus les réponses 403 et interrompt la création lorsqu'il ne peut pas lire/supprimer les ressources existantes. La vérification initiale prouve la validité du jeton ; les permissions effectives sont vérifiées par les appels réels et leurs erreurs contextualisées, pas par une liste de scopes fictive.
- **Runbook associé** : [03-cloudflare-permissions.md](../../docs/certification/incidents/03-cloudflare-permissions.md).

### 3.3 Démarrage de l'API FastAPI sans schéma initial (Neon DB)
- **Symptôme** : Au déploiement sur Hetzner, le conteneur de l'API FastAPI démarrait en boucle en levant des exceptions d'absence de relations de tables.
- **Cause** : L'API démarrait avant que les migrations d'initialisation de schéma Neon PostgreSQL gérées par Alembic ne soient finalisées.
- **Résolution** : le CD exécute les migrations avant la remise en ligne et attend les contrôles de santé après recréation. Il n'existe pas d'`entrypoint.sh` avec boucle wait-for-DB dans ce dépôt.
- **Runbook associé** : [04-neon-schema-deployment.md](../../docs/certification/incidents/04-neon-schema-deployment.md).

### 3.4 Dashboard Grafana vide (Collecte Alloy muette)
- **Symptôme** : Après déploiement de la stack de monitoring, les tableaux de bord Grafana restaient vides et n'affichaient aucune métrique ni log.
- **Cause** : plusieurs problèmes distincts ont été observés pendant l'intégration : droits lecture/écriture des jetons, labels de stack et coexistence des collecteurs Sicurre/Sicurre-ML.
- **Résolution** : séparation par label `stack`, jetons lecture/écriture dédiés, images Alloy épinglées et validation distante des cibles Prometheus. Les détails doivent être accompagnés des captures/requêtes conservées.
- **Validation externe** : le 17 juillet 2026, Grafana a retourné les quatre
  cibles Sicurre à `up=1` et les trois dashboards attendus via ses API de lecture.
- **Runbook associé** : [05-grafana-telemetrie-absente.md](../../docs/certification/incidents/05-grafana-telemetrie-absente.md).

---

## 4. Matrice de conformité et de preuves

| Critère d'évaluation | Preuve (Section / Fichier) | Statut |
|---|---|---|
| **Règles de filtrage télémétrique** | Configuration Alloy, requête distante du 07/08/2026 et capture infrastructure | `VALIDÉ` : 13,4k → 2 440 séries actives ; cAdvisor 10 437 → 43 |
| **Masquage PII** | suppression des labels à forte cardinalité, journaux sans corps d'e-mail et tests de rédaction | `VALIDÉ` |
| **Reproduction d'incident** | Page administrateur « Résilience » et déclencheur borné | `FONCTIONNEL` |
| **Résilience d'interface** | [test_inference.py](../../tests/unit/poc/test_inference.py) et `test_app.py` | `PASSED` localement ; figures à capturer |
| **Réversibilité production** | Figure E5-1 et journal daté du 18/07/2026 | `VALIDÉ` : rollback et restauration, trois surfaces HTTP 200 |

Le 7 août 2026, la limite gratuite Grafana a été traitée à la source. Le scrape
cAdvisor du serveur partagé exportait plus de dix mille séries, principalement
des familles TCP noyau et des labels de conteneurs sans utilité pour les SLO de
Sicurre. Un relabeling Alloy conserve uniquement le projet Compose Sicurre et
les familles nécessaires à la disponibilité, au CPU, à la mémoire, au réseau et
aux OOM. Après expiration des séries obsolètes, une requête Prometheus distante
a mesuré 2 440 séries actives au total, dont 43 pour cAdvisor. Les métriques API,
gateway, hôte, Alloy et Sicurre-ML sont restées disponibles.

Grafana contient dix-sept règles provisionnées par les deux dépôts. Les cinq
règles Sicurre couvrent disponibilité API, taux 5xx, latence, disponibilité
Alloy et exercice contrôlé. Une notification réelle `Sicurre API unavailable`
a été reçue le 6 août, puis l'interface a confirmé le retour de toutes les règles
à l'état `Normal`. Le CD automatique `31161749312` a ensuite validé release,
images, déploiement Hetzner, provisionnement Grafana et santé post-déploiement.

## 5. Preuve visuelle de reprise

![Rollback contrôlé et restauration](screenshots/e5-controlled-production-rollback.png)

*Figure E5-4 — Extrait synthétique fidèle du journal de production : retour de
`v1.4.2` à `v1.4.1`, santé app/API/auth, puis restauration de `v1.4.2`. La sonde
`000` documente la fenêtre de démarrage et la sonde suivante la reprise.*

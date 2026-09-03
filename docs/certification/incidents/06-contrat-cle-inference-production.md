# Incident 06 — Clé d'inférence absente du runtime API

## Contexte et symptôme

Le 17 juillet 2026 à 12:33 (Europe/Paris), un e-mail contrôlé portant le sujet
`SICURRE-E2E-20260717-01` a traversé Cloudflare Email Routing et a été livré à
la destination finale. Aucun événement correspondant n'était cependant visible
dans Sicurre et aucun appel n'apparaissait côté Sicurre-ML.

## Impact et comportement de sûreté

L'analyse n'a pas eu lieu. Le gateway a appliqué le comportement fail-open
documenté afin de ne pas perdre le courrier : livraison avec statut d'analyse en
échec, sans présenter le message comme classifié. Aucun résultat synthétique n'a
été écrit dans `threat_log` et aucun corps MIME brut n'a été conservé.

## Diagnostic

La corrélation temporelle du journal API a isolé l'erreur
`Illegal header value b'Bearer '`. La variable de production était nommée
`SICURRE_INFERENCE_API_KEY`, alors que `Settings` ne résolvait que
`INFERENCE_API_KEY`. Le client construisait donc un en-tête Bearer vide avant
toute requête réseau vers Sicurre-ML.

## Correction

1. La configuration typée accepte le nom canonique préfixé et conserve l'ancien
   nom comme alias de compatibilité.
2. Un test de régression charge explicitement le contrat de production.
3. Le secret du conteneur API a été resynchronisé avec Sicurre-ML.
4. Les longueurs et empreintes SHA-256 runtime correspondent sans afficher les
   clés.
5. Une sonde authentifiée depuis le conteneur API vers `/v1/classify` a retourné
   HTTP 200 avec un verdict conforme au contrat.

## Validation et preuve restante

La cause technique et la connectivité service-à-service sont résolues. Le même
message ne doit pas être rejoué puisqu'il n'a pas été conservé. La validation
E2E exige un nouvel e-mail au sujet unique, puis la corrélation de l'heure, de
l'événement Sicurre, du verdict ML et de la livraison finale. Jusque-là, C10
reste `PARTIEL`.

Une seconde tentative a ensuite atteint Sicurre-ML mais reçu HTTP 422. Le contrat
d'entrée Sicurre autorise un sujet de 500 caractères, une projection MIME de
5 500 caractères et un corps vide lorsque sujet/expéditeur portent le signal.
Sicurre-ML limitait respectivement à 300, 4 096 et `min_length=1`. La décision
d'architecture est de conserver l'enveloppe d'ingress et d'élargir le schéma ML ;
la fenêtre de tokens du modèle reste gérée à l'intérieur du pipeline ML.

## Prévention

- centraliser les noms de variables dans `Settings` et les exemples Compose ;
- tester les noms réellement injectés en production ;
- ajouter au préflight un appel authentifié sans contenu client vers le ML ;
- alerter sur les échecs sans journaliser e-mails, clés ou autorisations.

### État des mesures au 3 septembre 2026

Les deux premières mesures étaient acquises depuis PR #80. Les deux suivantes
ne l'étaient pas, et leur absence rendait l'incident reproductible à
l'identique : rien dans la supervision ne distinguait « le classifieur est en
bonne santé » de « le classifieur refuse nos identifiants ».

**Sonde authentifiée.** `_probe_inference_runtime` n'interrogeait que
`/v1/health` et `/v1/ready`, qui répondent sans identifiants et sont donc
restés verts pendant tout l'incident. Le composant `inference_contract`
effectue désormais un `POST /v1/classify` portant l'en-tête `Authorization`
réellement utilisé par la passerelle, et signale `down` sur 401/403. La charge
utile est synthétique (`probe@sicurre.invalid`, `use_llm` et `use_virustotal`
à `false`) : consulter la page d'administration ne doit pas retraiter le
message d'un client, ni dépenser de quota tiers.

**Alerte.** Aucune métrique ne comptait les scans en échec : `observe_scan`
n'est atteint qu'une fois le verdict obtenu, si bien qu'un scan échoué
n'apparaissait pas comme échec dans `sicurre_scan_total` — il n'y apparaissait
pas du tout. `sicurre_scan_failure_total` compte désormais ces scans sous un
ensemble fermé de raisons dérivées du type d'exception, jamais de son message,
qui peut contenir une URL ou un fragment du courrier analysé. La règle
« Sicurre email scans are failing » se déclenche à partir de trois échecs en
dix minutes ; la règle 5xx existante exigeait vingt requêtes en quinze minutes
avant même d'être évaluée, seuil que le trafic de démonstration n'atteint
jamais.

## Validation et preuve restante

La cause technique et la connectivité service-à-service sont résolues. Le même
message ne doit pas être rejoué puisqu'il n'a pas été conservé.

**Vérification du 3 septembre 2026.** Contre la production, `/v1/health` et
`/v1/ready` ont répondu `200` tandis qu'un `POST /v1/classify` porteur d'une
clé non-production a répondu `401`. C'est la signature exacte de l'incident, et
elle confirme par l'observation que les deux sondes non authentifiées ne
peuvent pas la détecter, là où `inference_contract` la signale.

**Ce qui reste à faire.** La validation E2E complète exige l'envoi d'un
nouvel e-mail au sujet unique, puis la corrélation de l'heure, de l'événement
Sicurre, du verdict ML et de la livraison finale. Cet envoi n'a pas été
effectué ici : il émet un courrier réel depuis le domaine de production et
relève d'une décision de l'exploitant, non d'une vérification automatisable.
**C10 reste donc `PARTIEL`** — le motif est désormais l'absence de rejeu, non
plus un défaut non corrigé.

## Traçabilité

PR #80 · commit `5857b49` · 18 juillet 2026
Sonde authentifiée, métrique d'échec et alerte : branche
`fix/data-governance-and-drop-reasons`, 3 septembre 2026. Tests :
`tests/unit/app/test_runtime_health_probes.py` (dont
`test_contract_probe_catches_the_incident_06_condition`, qui reproduit la
signature santé-verte/classification-refusée) et
`tests/unit/app/test_scan_failure_metric.py`.

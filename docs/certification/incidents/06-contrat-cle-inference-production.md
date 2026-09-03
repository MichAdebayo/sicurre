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

## Traçabilité

PR #80 · commit `5857b49` · 18 juillet 2026

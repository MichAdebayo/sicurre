# Incident supplémentaire — Provisionnement Cloudflare refusé

## Constat

Le scénario Vinse a atteint la dernière étape de provisionnement puis Cloudflare a
retourné une erreur d'autorisation. L'ancienne logique pouvait assimiler un 403 à
une ressource déjà activée et poursuivre, laissant une configuration partielle.

## Cause

Le jeton était reconnu mais ne disposait pas de toutes les permissions nécessaires
aux opérations réellement demandées : lecture/écriture Email Routing, Worker,
règles et, selon l'audit DNS, enregistrements de zone.

## Correction implémentée

- `verify_token` confirme uniquement que Cloudflare reconnaît le jeton ; elle ne
  prétend pas énumérer les scopes ;
- chaque opération conserve le statut et le message Cloudflare dans une
  `CloudflareAPIError` contextualisée ;
- un 403 n'est plus assimilé à « déjà activé » ;
- une lecture ou suppression de conflit impossible interrompt la création afin
  d'éviter les doublons ;
- les payloads Worker/règle et les chemins d'erreur font l'objet de tests.

## Non-régression

Les tests `test_enable_email_routing_surfaces_permission_error`,
`test_rule_creation_aborts_when_conflicts_cannot_be_read`,
`test_destination_creation_aborts_when_existing_addresses_cannot_be_read` et
`test_unwrap_rejects_http_and_contract_errors` prouvent l'échec fermé.

La preuve finale doit ajouter un pré-vol et deux provisionnements idempotents sur
le compte Vinse réel, sans afficher le jeton ni modifier une ressource hors Sicurre.

## Validation externe du 17 juillet 2026

Le contrôle réel a distingué validité du jeton et autorisations par capacité :

- validation du jeton et recherche de la zone `vinse.app` : HTTP 200 ;
- lecture des règles : cinq règles, dont `Sicurre Intercept` active et reliée au
  Worker ;
- lecture du Worker : HTTP 200, URL de scan
  `https://sicurre.com/v1/email/scan` et secret partagé présents ;
- diagnostic administrateur Sicurre : inférence, gateway, binding Worker et
  règle de routage à l'état `ok` ;
- lecture Cloudflare Email Sending : HTTP 403, code fournisseur 10000. Le
  diagnostic Sicurre expose donc `Cloudflare Email Sending: Edit permission is
  missing` au lieu d'une erreur d'authentification générique.

Le provisionnement entrant est fonctionnel. La libération d'un faux positif par
Email Sending reste bloquée jusqu'à l'ajout de cette permission, puis doit être
testée sur un message contrôlé.

## Traçabilité

PR #67 · commit `3979746` · merge `ff7ef70` · 17 juillet 2026

Le même commit corrige l'incident 01. Il introduit
`test_enable_email_routing_surfaces_permission_error`, qui couvre la remontée du
403 Cloudflare comme erreur de permission plutôt que comme « déjà activé ».

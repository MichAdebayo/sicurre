# Incident principal — Indisponibilité de l'API d'inférence locale

## 1. Résumé

Le POC appelle Sicurre-ML sur la route authentifiée `POST /v1/classify`. Une URL
erronée, une clé absente/refusée ou un processus arrêté empêche l'inférence réelle.
Les modes `live`, `simulation` et `incident` sont explicites et ne basculent jamais
silencieusement de l'un à l'autre.

## 2. Impact

- aucune décision réelle ne doit être produite ou persistée ;
- le POC doit expliquer l'indisponibilité sans exposer le secret ;
- la simulation ne doit jamais être présentée comme une sortie modèle ;
- le texte saisi doit rester disponible pour une reprise contrôlée.

## 3. Incident observé le 17 juillet 2026

Le POC chargeait `SICURRE_POC_INFERENCE_API_KEY` et envoyait correctement le
Bearer. Le processus Sicurre-ML chargeait `INFERENCE_API_KEY` depuis son propre
dépôt avec une valeur différente. `/health` restait vert car cette route ne
validait pas le secret ; le premier `POST /v1/classify` retournait donc `401` avec
la catégorie `invalid_bearer`.

La comparaison a été réalisée par empreinte et longueur uniquement : aucune clé
n'a été imprimée dans les journaux ou le dossier de preuve.

## 4. Correction

1. Le contrat de ce dépôt reste exclusivement `SICURRE_POC_*`.
2. Au lancement local de Sicurre-ML, la valeur POC est injectée sous le nom attendu
   par ce service : `INFERENCE_API_KEY`.
3. Le pré-vol vérifie d'abord `/health`, puis envoie `{}` à `/v1/classify` avec le
   Bearer. `422` prouve que l'authentification a passé sans exécuter le modèle ;
   `401` produit « Clé d'inférence locale refusée ».
4. Le client `httpx` conserve un timeout borné (35 secondes par défaut dans le
   POC) et transforme réseau, HTTP et contrat invalide en exceptions typées.

Voir [config.py](../../../src/poc/config.py),
[inference.py](../../../src/poc/inference.py) et
[README.md](../../../src/poc/README.md).

## 5. Reproduction contrôlée C20/C21

1. Démarrer Sicurre-ML avec le mapping de clé documenté, puis le POC.
2. Vérifier « Service local disponible et authentifié ».
3. Exécuter une classification `live` et conserver le verdict/latence sans contenu
   sensible dans la capture.
4. Ouvrir **Résilience**, choisir le scénario à exercer et lancer la requête de test.
5. Comparer le défaut attendu au statut réellement observé (`401`, `422` ou
   erreur de connexion selon le scénario).
6. Vérifier le contrôle automatique de disponibilité après incident, puis
   revenir au **Modèle local** et confirmer une classification nominale.

## 6. Non-régression

| Scénario | Test automatisé | Résultat local |
|---|---|---|
| Bearer et normalisation | `test_live_mode_sends_bearer_key_and_normalizes_response` | passé |
| Bearer refusé | `test_live_authentication_failure_is_contextual` | passé |
| Pré-vol authentifié/refusé | `test_health_reports_success_and_http_failure`, `test_health_reports_rejected_bearer_key` | passé |
| Défauts bornés (`401`, `422`) | `test_fault_probes_exercise_real_request_boundaries` | passé |
| Point d'accès injoignable | `test_health_reports_network_failure`, `test_live_network_failure_is_contextual` | passé |
| Réseau indisponible | `test_live_network_failure_is_contextual` | passé |

Le 17 juillet 2026, le pré-vol réel a réussi et une classification ONNX a retourné
`source=live`, `label_verdict=legitimate`. Les captures avant/incident/reprise et
la trace console anonymisée restent à insérer dans le dossier illustré.

## Traçabilité

PR #67 · commit `3979746` · 17 juillet 2026

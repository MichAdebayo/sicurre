# Dossier de certification Sicurre

Ce répertoire regroupe les pièces versionnées qui soutiennent les cinq rapports
remis au jury (titre RNCP 37827, Développeur en intelligence artificielle).
Les rapports eux-mêmes (Word et PDF, en français) ne sont pas versionnés ; ils
sont conservés localement sous `evaluation-word/pre-submit/claude/E1` à `E5`.

## Contenu

| Pièce | Fichier | Rôle |
|---|---|---|
| Incidents | [`incidents/01`](incidents/01-inference-locale-indisponible.md) à [`07`](incidents/07-monitoring-validation.md) | Un dossier par incident : constat, cause, reproduction, correction, tests, traçabilité (PR, commit, date) |
| Registre de veille | [`annexes/registre-veille.md`](annexes/registre-veille.md) | Les 21 séances de veille, sources qualifiées et décisions (E2, C6) |
| Spécification métier | [`sicurre_business_specification_v2.md`](sicurre_business_specification_v2.md) | Cadrage initial du produit et de ses contraintes |

Les incidents 01 et 06 (clé d'inférence, 17 juillet 2026) forment l'incident
principal du rapport E5. L'incident 07 documente la validation de la chaîne
d'alerte Grafana par deux exercices contrôlés.

## Règles de preuve

1. Chaque affirmation technique renvoie vers un fichier, une commande, un test,
   une capture ou un résultat daté.
2. Les secrets, contenus d'e-mails et données personnelles sont masqués.
3. Les captures portent un numéro, une date, un texte alternatif et une légende.
4. Les écarts entre conception et réalisation sont documentés comme décisions
   d'architecture (`docs/adr/`).

## Captures disponibles (local, `screenshots/`)

| Preuve | Fichier | Usage |
|---|---|---|
| Logs application | `Drilldown logs/sicurre app.png` | Gateway et trafic applicatif |
| Logs API | `Drilldown logs/sicurre api.png` | Diagnostic backend et incident Bearer |
| Logs authentification | `Drilldown logs/auth service.png` | Better Auth isolé |
| Logs Alloy Sicurre | `Drilldown logs/alloy.png` | Acheminement de télémétrie |
| Logs ML | `Drilldown logs/sicurre ml inference.png` | Inférence et défaut de scrape 400 |
| Logs Alloy ML | `Drilldown logs/sicurre ml alloy.png` | Collecteur ML séparé |
| Traces | `Drilldown traces/sicurre trace.png` | Services, erreurs et durées Tempo |
| Rollback | `e5-controlled-production-rollback.png` | Reprise `v1.4.1` puis restauration `v1.4.2` |
| Règles Grafana | `grafana-alert-rules-2026-08-07.png` | Règles Sicurre provisionnées et revenues à `Normal` |
| Infrastructure Grafana | `grafana-infrastructure-health-2026-08-07.png` | CPU, mémoire, disque et collecteur hôte |

Les captures présentées masquent comptes, adresses e-mail, jetons, identifiants
de messages et identifiants de traces lorsqu'ils ne sont pas utiles.

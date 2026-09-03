# Dossier de certification Sicurre

## Statut du dossier

Ce répertoire rassemble les cinq livrables attendus par le référentiel Simplon. Il est volontairement ignoré par Git pendant la phase de rédaction et de revue. Les documents distinguent systématiquement :

- les objectifs initiaux ;
- les décisions prises pendant le projet ;
- l'implémentation effectivement vérifiée ;
- les preuves encore à capturer.

Une case `À capturer` n'est pas une preuve. Elle empêche qu'un résultat non observé soit présenté comme acquis.

## Livrables

La synthèse transversale se trouve dans
[`00-matrice-tracabilite-c1-c21.md`](00-matrice-tracabilite-c1-c21.md). Elle doit
être relue avant chaque remise pour éviter qu'un état `PARTIEL` soit présenté
comme une preuve acquise.

Le déroulé reproductible de la démonstration et la liste des figures attendues
se trouvent dans [`06-script-soutenance.md`](06-script-soutenance.md).

| Évaluation | Compétences | Document | Cible indicative |
|---|---|---|---:|
| E1 | C1 à C5 | `01-e1-plateforme-donnees-c1-c5.md` | 14–18 pages |
| E2 | C6 à C8 | `02-e2-veille-et-service-ia-c6-c8.md` | 8–12 pages |
| E3 | C9 à C13 | `03-e3-api-modele-et-mlops-c9-c13.md` | 12–16 pages |
| E4 | C14 à C19 | `04-e4-application-ia-c14-c19.md` | 16–22 pages |
| E5 | C20 à C21 | `05-e5-monitorage-et-incident-c20-c21.md` | 10–14 pages |

Ces volumes sont des repères éditoriaux, pas une exigence du référentiel. La cible globale de 60 à 80 pages inclut les schémas, tableaux et captures.

## Règles de preuve

1. Chaque affirmation technique renvoie vers un fichier, une commande, un test, une capture ou un résultat daté.
2. Les secrets, contenus d'e-mails et données personnelles sont masqués.
3. Les captures disposent d'une légende, d'un texte alternatif et d'une date.
4. Les écarts entre conception et réalisation sont documentés comme décisions d'architecture.
5. La démonstration principale C20/C21 porte sur l'indisponibilité de l'API d'inférence locale. Les autres incidents sont des preuves complémentaires.

## Inventaire des captures disponibles

| Preuve | Fichier | Usage |
|---|---|---|
| Logs application | `screenshots/Drilldown logs/sicurre app.png` | Gateway et trafic applicatif |
| Logs API | `screenshots/Drilldown logs/sicurre api.png` | Diagnostic backend et incident Bearer |
| Logs authentification | `screenshots/Drilldown logs/auth service.png` | Better Auth isolé |
| Logs Alloy Sicurre | `screenshots/Drilldown logs/alloy.png` | Acheminement de télémétrie |
| Logs ML | `screenshots/Drilldown logs/sicurre ml inference.png` | Inférence et défaut de scrape 400 |
| Logs Alloy ML | `screenshots/Drilldown logs/sicurre ml alloy.png` | Collecteur ML séparé |
| Traces | `screenshots/Drilldown traces/sicurre trace.png` | Services, erreurs et durées Tempo |
| Rollback | `screenshots/e5-controlled-production-rollback.png` | Reprise `v1.4.1` puis restauration `v1.4.2` |
| Règles Grafana | `screenshots/grafana-alert-rules-2026-08-07.png` | Règles Sicurre provisionnées et revenues à `Normal` |
| Infrastructure Grafana | `screenshots/grafana-infrastructure-health-2026-08-07.png` | CPU, mémoire, disque et collecteur hôte réels |

Les captures finales doivent masquer comptes, adresses e-mail, tokens,
identifiants de messages et identifiants de traces lorsqu'ils ne sont pas utiles.

## Parcours de soutenance POC

1. Démarrer l'API ML locale et le POC avec le contrat `SICURRE_POC_*`.
2. Montrer la classification réelle via `/v1/classify`.
3. Montrer une simulation explicitement étiquetée, sans la confondre avec le modèle.
4. Choisir un scénario de résilience, exécuter la requête fautive et comparer
   le statut attendu au statut observé.
5. Montrer le contrôle de disponibilité post-incident, puis revenir au modèle
   local et confirmer une classification nominale.
6. Présenter le rejeu de base, le cron isolé et l'aperçu de release sans écriture de production.

Le graphique de filiation distingue les sources réellement enregistrées. Pour
la base V1 récupérée, il affiche honnêtement les familles de reconstruction car
le fournisseur ligne par ligne n'a pas pu être restauré. Une nouvelle collecte
montre ensuite sa source réelle et constitue la preuve incrémentale attendue.

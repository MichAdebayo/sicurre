# Script de soutenance Sicurre

## Préparation hors temps de présentation

1. Vérifier les variables `SICURRE_POC_*` sans afficher leur valeur.
2. Lancer `make poc-inference`, puis `make poc` dans un second terminal.
3. Ouvrir le POC en navigation privée ou supprimer seulement la session POC.
4. Préparer Grafana sur les dashboards Sicurre et Sicurre-ML, avec une fenêtre
   temporelle contenant la démonstration mais aucune donnée personnelle.
5. Garder les artefacts CI, le schéma d'architecture et la version Kaggle dans
   des onglets séparés. Ne jamais ouvrir `.env` devant le jury.

## Parcours principal — 20 minutes

### 0:00–2:00 — Besoin et résultat attendu

- Présenter les TPE francophones sans équipe sécurité comme cible.
- Expliquer les deux couches : DMARC protège l'identité d'expédition ; Sicurre
  classe le contenu reçu et permet la remédiation.
- Annoncer le chemin de preuve : données, modèle local, application, incident,
  monitorage et livraison.

### 2:00–5:00 — C1 à C5 : plateforme de données

- Ouvrir « Jeux de données » : distinguer les 34 066 enregistrements bruts des
  32 288 messages normalisés et des 32 288 éléments de la version figée.
- Sélectionner la collecte SEKOIA à 640 lignes, puis sa réexécution à 0 : le
  premier résultat prouve la collecte locale d'IOC ; le second prouve
  l'idempotence. Aucun des deux n'est présenté comme un e-mail d'entraînement.
- Expliquer honnêtement les quatre familles de reconstruction V1. Elles ne sont
  pas les fournisseurs originaux ; une nouvelle collecte conserve sa source.
- Montrer le flux : collectes par cadence, release mensuelle distincte, Kaggle,
  puis dispatch Sicurre-ML.
- Montrer l'OpenAPI `/v1/data/*` et une PR CI verte.

### 5:00–7:00 — C6 à C8 : veille et choix IA

- Ouvrir le registre daté : auteur, date, fiabilité, synthèse, décision.
- Présenter les trois candidats et la limite actuelle : le protocole comparatif
  est défini, mais aucune mesure non produite ne doit être annoncée.
- Montrer le préflight POC : SQLite isolé, clé présente, `/v1/classify` accepté.

### 7:00–10:00 — C9 à C13 : modèle et MLOps

- Dans « Espace d'essai », choisir « Modèle local » et analyser un scénario.
- Montrer label, score, latence et version retournée ; préciser que le POC appelle
  réellement le dépôt Sicurre-ML sur `/v1/classify`.
- Montrer ensuite « Simulation » et rappeler qu'elle est explicitement étiquetée,
  donc jamais présentée comme une prédiction du modèle.
- Présenter la CI/CD ML, l'image SHA et la séparation code/modèle/dataset.

### 10:00–13:00 — C14 à C19 : application et feedback

- Parcourir Accueil, Smail et Journal des menaces.
- Démontrer un faux positif : corriger un blocage, puis retrouver le message dans
  Smail. Démontrer un faux négatif : signaler un message livré, puis le retrouver
  dans le journal.
- Montrer les thèmes clair/sombre, les rôles administrateur/utilisateur et les
  états contextualisés. Ne pas présenter le POC comme l'application React : il
  prouve la faisabilité locale avant le produit complet.

### 13:00–17:00 — C20/C21 : incident principal

1. Ouvrir la page administrateur « Résilience ».
2. Choisir « Clé d'accès refusée », exécuter le scénario et montrer le `401`
   attendu, réellement retourné par l'API locale.
3. Rejouer « Requête incomplète » (`422`) ou « Point d'accès injoignable »
   (erreur de connexion) selon le temps disponible.
4. Montrer la comparaison attendu/observé et le contrôle de disponibilité
   exécuté après chaque défaut.
5. Expliquer que chaque scénario affecte une requête de test sans interrompre
   le serveur partagé ni persister une fausse prédiction.
6. Corréler l'heure avec métriques/traces, puis présenter le dossier incident :
   cause, reproduction, correction, test, prévention et commit.

### 17:00–19:00 — Flux protégé et livraison

- Ouvrir « Flux de données » et lire les trois périmètres avant de cliquer.
- Rejeu : SQLite POC seulement. Cron : lecture publique, SQLite et snapshots
  locaux sous `data/local/poc`. Aperçu idempotent : local, sans Kaggle ni dispatch ML.
- Montrer les branches protégées, CI parallèle, CD séquentielle, images SHA,
  santé post-déploiement et procédure de rollback.

### 19:00–20:00 — Conclusion et limites

- Résumer : classification francophone, runtime privé, feedback tenant-safe,
  données versionnées, observabilité et incident reproductible.
- Énoncer les preuves encore externes si elles ne sont pas capturées : premier
  cycle mensuel, e-mail réel Vinse, permission Email Sending et benchmark C7.
- Ne jamais transformer une feuille de route en résultat acquis.

## Captures obligatoires

| Figure | Écran | Preuve attendue |
|---|---|---|
| F1 | Préflight paramètres | isolation locale et service accepté, aucun secret |
| F2 | Classification réelle | entrée anonymisée, verdict, score, latence, version |
| F3 | Dataset | volumes, sources, note V1 et version gelée |
| F4 | Faux positif | correction puis apparition dans Smail |
| F5 | Faux négatif | signalement puis apparition dans le journal |
| F6 | Incident | message contextualisé sans résultat fabriqué |
| F7 | Reprise | même scénario réussi après retour au mode local |
| F8 | Grafana | métrique/trace corrélée à la fenêtre de l'incident |
| F9 | CI/CD | PR verte et déploiement immuable réussi |
| F10 | Production | Cloudflare, dashboard/admin et état de santé |

Chaque capture reçoit un numéro, une date, un texte alternatif et une légende
expliquant ce qu'elle prouve. Les adresses personnelles, tokens, identifiants de
messages et contenus d'e-mail sont masqués.

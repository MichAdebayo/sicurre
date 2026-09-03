# Incident supplémentaire — API démarrée sans schéma Neon

## Constat

Le premier déploiement de l'API échouait avec des relations absentes : la base Neon
ciblée ne contenait pas encore les schémas de la plateforme de données et de
l'application.

## Cause

Le conteneur ne peut servir l'API avant l'application des deux chaînes Alembic.
Le problème n'était pas un `entrypoint.sh` défectueux : aucun fichier de ce nom
n'existe dans le runtime.

## Correction implémentée

La commande du service `sicurre-api` dans `docker-compose.prod.yml` est séquentielle :

1. `alembic upgrade head` ;
2. `alembic -c alembic.app.ini upgrade head` ;
3. démarrage Uvicorn uniquement si les deux commandes précédentes réussissent.

Le CD recrée ensuite la stack et effectue jusqu'à 30 contrôles du gateway et de
l'API. Une migration en échec empêche donc le service d'être déclaré sain.

## Validation externe du 17 juillet 2026

La production a été observée après exécution de cette séquence : l'API et Better
Auth étaient sains, les contrats `/health` et `/api/auth/ok` répondaient en HTTP
200, et une connexion administrateur réelle a lu les tables applicatives via
`/v1/admin/overview`. Better Auth a également confirmé son dialecte PostgreSQL,
la présence du compte propriétaire configuré et l'émission d'une session.

Cette preuve confirme que les deux schémas sont exploitables. La capture du job
CD montrant les sorties Alembic reste une annexe utile, mais elle n'est plus la
seule preuve du schéma déployé.

## Traçabilité

Commit `e45da80` · merge `a5ef3ba` (« Merge develop into main for first
production deployment ») · 11 juillet 2026

**Pas de numéro de PR.** La séquence Alembic du service `sicurre-api` dans
`docker-compose.prod.yml` est arrivée sur `main` par une fusion directe
`develop → main` lors du premier déploiement de production, avant que le flux
par pull request ne soit systématique. Le champ est laissé vide plutôt que
rempli d'un numéro plausible.

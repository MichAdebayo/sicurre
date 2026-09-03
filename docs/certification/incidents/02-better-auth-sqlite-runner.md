# Incident supplémentaire — Better Auth et répertoire SQLite absent

## Constat

Sur un runner CI vierge, `better-sqlite3` échouait lorsque le chemin local pointait
vers un dossier qui n'existait pas. Le poste de développement masquait ce défaut
car `data/local/` était déjà présent.

## Cause

`better-sqlite3` crée le fichier SQLite, pas son répertoire parent. La configuration
locale supposait donc un état du système de fichiers non garanti en CI.

## Correction implémentée

- `auth-service/auth.ts` résout `SICURRE_LOCAL_BETTER_AUTH_DB_PATH` puis appelle
  `mkdirSync(path.dirname(...), { recursive: true })` avant `new Database(...)`.
- la production refuse cette variable locale et exige
  `SICURRE_BETTER_AUTH_DATABASE_URL` vers Neon ; les deux modes ne peuvent pas se
  mélanger ;
- `createAuthApp` reçoit le dialecte et le handler, ce qui rend le contrat HTTP
  testable sans ouvrir un listener réseau.

## Preuve attendue

Joindre le run CI final et le test Better Auth exécuté avec un répertoire temporaire
absent au départ. Un run « tous les tests passés » ne doit pas être reformulé en
« 100% de couverture » sans artefact de couverture correspondant.

## Traçabilité

PR #54 · commit `570243b` · merge `1d9c5f9` · 14 juillet 2026

Le commit ajoute l'import `mkdirSync`, l'appel
`mkdirSync(path.dirname(resolvedLocalDatabasePath), { recursive: true })` avant
`new Database(...)`, et le découplage de `createAuthApp` décrits ci-dessus.

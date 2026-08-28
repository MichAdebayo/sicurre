# Sicurre POC local

Le POC Streamlit démontre la validation locale de Sicurre avant l'application SaaS. Il utilise son propre contrat de configuration et ne doit jamais dépendre implicitement des variables de production.

## Variables requises

```dotenv
SICURRE_POC_DATABASE_URL="sqlite+aiosqlite:////chemin/absolu/data/local/sicurre_poc.db"
SICURRE_POC_DATA_PLATFORM_DATABASE_URL="sqlite+aiosqlite:////chemin/absolu/data/local/sicurre_dataplatform.db"
SICURRE_POC_INFERENCE_API_URL="http://127.0.0.1:8000/v1/classify"
SICURRE_POC_INFERENCE_API_KEY="..."
SICURRE_POC_ADMIN_EMAIL="admin.local@sicurre.test"
SICURRE_POC_ADMIN_PASSWORD="..."
SICURRE_POC_ADMIN_NAME="Administrateur Sicurre"
SICURRE_POC_VIEWER_EMAIL="viewer.local@sicurre.test"
SICURRE_POC_VIEWER_PASSWORD="..."
SICURRE_POC_VIEWER_NAME="Utilisateur Démo"
```

Les deux URL de base doivent être SQLite. L'URL d'inférence doit cibler
`/v1/classify` sur `localhost`, `127.0.0.1` ou `::1`.

## Stockage local optionnel

```dotenv
SICURRE_POC_SNAPSHOT_PREFIX="demonstrations/poc"
SICURRE_POC_SNAPSHOT_DIR="data/local/poc/snapshots"
```

Le cron de démonstration lit le flux public SEKOIA, puis écrit son snapshot,
sa lignée et ses nouveaux enregistrements uniquement dans ce répertoire et la
base SQLite POC. Une seconde exécution ignore les indicateurs déjà présents.

Le POC ne contient aucun chemin de publication Kaggle ni de dispatch ML. Ses
trois opérations de données sont limitées à SQLite et au stockage local ; seul
le cron SEKOIA effectue une lecture externe du flux public.

## Démarrage

```bash
# Terminal 1, dans ce dépôt
# Le lanceur transmet explicitement la clé POC au processus Sicurre-ML.
make poc-inference

# Terminal 2, dans ce dépôt
make poc
```

Les deux dépôts conservent volontairement des noms distincts :
`SICURRE_POC_INFERENCE_API_KEY` appartient au contrat de démonstration de Sicurre,
tandis que Sicurre ML reçoit `INFERENCE_API_KEY`. Leur valeur doit être identique
pour le processus local. Le pré-vol du POC vérifie à la fois `/health` et
l'acceptation de la clé sans exécuter le modèle ; une clé différente est signalée
comme refusée avant la démonstration.

`SICURRE_ML_REPO` permet de remplacer le chemin frère par défaut
`../sicurre-ml` si le dépôt ML se trouve ailleurs.

Le POC propose trois modes d'inférence :

- **Modèle local** : appel authentifié réel ;
- **Simulation** : résultat déterministe explicitement étiqueté ;
- **Incident contrôlé** : indisponibilité reproductible pour C20/C21.

Il n'existe aucun fallback silencieux entre ces modes.

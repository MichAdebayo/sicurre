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

Les deux URL de base doivent être SQLite. L'URL d'inférence doit cibler exactement `/v1/classify`.

## Variables externes optionnelles

```dotenv
SICURRE_POC_ALLOW_EXTERNAL_WRITES=false
SICURRE_POC_ALLOW_ML_DISPATCH=false
SICURRE_POC_R2_PREFIX="demonstrations/poc"
SICURRE_POC_KAGGLE_DATASET_SLUG=""
```

Par défaut, aucune écriture externe n'est autorisée. Le cron de démonstration SEKOIA exige l'activation explicite des écritures et stocke uniquement sous `demonstrations/...`. La publication Kaggle exige un slug de staging distinct. Le dispatch ML est interdit depuis la publication de démonstration.

## Démarrage

```bash
# Terminal 1, dans le dépôt Sicurre ML
# Démarrer l'API locale sur le port configuré.

# Terminal 2, dans ce dépôt
make poc
```

Le POC propose trois modes d'inférence :

- **Modèle local** : appel authentifié réel ;
- **Simulation** : résultat déterministe explicitement étiqueté ;
- **Incident contrôlé** : indisponibilité reproductible pour C20/C21.

Il n'existe aucun fallback silencieux entre ces modes.


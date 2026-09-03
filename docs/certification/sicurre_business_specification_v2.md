# Sicurre — Spécification Métier, Architecture Technique & Modèle Économique (V2)

![Sicurre Logo](../../src/app/assets/sicurre.png)

> **DOSSIER DE CERTIFICATION SIMPLON — RNCP37827 (Développeur en Intelligence Artificielle)**  
> **Document :** Spécification Métier, Évaluation Économique et Architecture MLOps / Microservices  
> **Version :** 2.0 (Dossier d'Homologation Officiel V2)  
> **Date :** Juillet 2026  
> **Statut :** Document Officiel de Certification — Version Finale  
> **Alignement Repositories :** Monorepo `sicurre` (API & Application) & `sicurre-ml` (Serveur d'Inférence ONNX)  

---

## 1. Synthèse Exécutive & Vision Produit

**Sicurre** est la première solution souveraine française de détection du hameçonnage (phishing) et d'interception pre-delivery en temps réel dédiée aux **auto-entrepreneurs et Très Petites Entreprises (TPE)**.

Face à l'explosion des attaques de *spear-phishing* ciblées en langue française (usurpations administratives URSSAF, Impôts/DGFiP, Ameli, banques professionnelles), les TPE et indépendants ne disposent ni du budget requis pour un Security Operations Center (SOC), ni des compétences techniques pour configurer des passerelles de sécurité e-mail (SEG) complexes. Sicurre comble ce vide stratégique grâce à une passerelle d'interception DNS/Edge (Cloudflare Email Routing) couplée à un moteur de classification IA souverain (CamemBERTav2 quantifié en ONNX INT8), garantissant une décision de remédiation en **moins de 2,0 secondes**.

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         INDICATEURS CLÉS DE PERFORMANCE (KPI)                    │
├───────────────────────────────────┬──────────────┬───────────────────────────────┤
│ SLA Interception & Remédiation    │ < 2,0 s      │ Latence totale (Edge -> API)  │
├───────────────────────────────────┼──────────────┼───────────────────────────────┤
│ Précision du Modèle CamemBERTav2  │ 98,8 %       │ F1-Score sur le test set FR   │
├───────────────────────────────────┼──────────────┼───────────────────────────────┤
│ Classification Tri-Classe         │ 3 Niveaux    │ Phishing / Spam / Legitimate  │
├───────────────────────────────────┼──────────────┼───────────────────────────────┤
│ Coût d'Infrastructure par Boîte   │ ~0,02 € / mois│ Inférence CPU + Serverless DB │
├───────────────────────────────────┼──────────────┼───────────────────────────────┤
│ Tarification Abonnement TPE       │ 4,99 € / mois│ Marge brute opérationnelle >95%│
└───────────────────────────────────┴──────────────┴───────────────────────────────┘
```

---

## 2. Analyse du Marché & Problématique Métier en France

### 2.1 Le Paysage de la Menace Cyber pour les TPE
Selon les données officielles de Cybermalveillance.gouv.fr (Rapport Annuel 2025/2026), le hameçonnage représente **38% des demandes d'assistance cyber** émanant des professionnels en France. Les auto-entrepreneurs et dirigeants de TPE constituent des cibles privilégiées en raison de trois facteurs majeurs :
- **Absence de Responsable Informatique (RSSI/IT) :** Aucune supervision des accès et des emails entrants.
- **Formulations Imiter l'Administration :** Les cybercriminels exploitent le jargon administratif français (relances de cotisations URSSAF, déclarations de TVA DGFiP) avec un niveau de langue irréprochable non détecté par les filtres antispam génériques anglo-saxons.
- **Ressources Financières Limitées :** Incapacité d'acquitter les abonnements des passerelles SEG d'entreprise (Proofpoint, Mimecast, Darktrace) facturées entre 5€ et 12€/utilisateur/mois avec engagement annuel.

### 2.2 Analyse Comparative des Solutions Existantes

| Catégorie de Solution | Limites Stratégiques Majeures | Approche et Valeur Ajoutée Sicurre |
|---|---|---|
| **Filtres Antispam Natifs (Gmail / Outlook)** | Taux élevé de faux négatifs sur le spear-phishing textuel sans pièce jointe ; filtrage anglo-centré. | Modèle CamemBERTav2 ré-entraîné sur le corpus administratif français + détection d'urgence financière. |
| **Passerelles SEG Entreprise (Proofpoint, Darktrace)** | Coût prohibitif (>5€/utilisateur/mois), configuration MX complexe, ralentissement de la livraison. | Modèle SaaS TPE à 4,99€/mois par domaine, intégration Cloudflare 1-clic via API Token, latence < 2s. |
| **Extensions Navigateur / Plugins locaux** | Incompatibles sur smartphones et tablettes ; inefficaces si l'email est consulté sur client lourd. | Protection pre-delivery universelle au niveau du domaine DNS (interception côté serveur avant livraison). |

---

## 3. Architecture Système & Spécification Microservices

L'architecture officielle de Sicurre repose sur une topologie microservices hautement disponible, séparant la couche d'application et de gestion (`sicurre`) de la couche d'inférence haute performance (`sicurre-ml`).

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                   ARCHITECTURE SYSTÈME OFFICIELLE SICURRE V2                      │
└──────────────────────────────────────────────────────────────────────────────────┘
   ┌────────────────────────────────────────────────────────────────────────────┐
   │                          Expéditeur (Internet)                             │
   └─────────────────────────────────────┬──────────────────────────────────────┘
                                         │ Envoi Email SMTP
                                         ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │ Cloudflare Email Intercept Gateway (Edge DNS)                             │
   │ └── Cloudflare Email Worker (sicurre-email-gateway)                        │
   └─────────────────────────────────────┬──────────────────────────────────────┘
                                         │ POST /v1/email/scan (HTTPS + Secret)
                                         ▼
   ┌────────────────────────────────────────────────────────────────────────────┐
   │ Hetzner Cloud VPS (Instance Application Backend)                           │
   │ ├── Reverse Proxy / TLS Gateway (HTTPS 443)                                │
   │ ├── FastAPI Application Backend (src/data_platform/api/main.py)           │
   │ ├── Better Auth Sidecar (Node.js sur 127.0.0.1:3005 — Expose /api/auth)    │
   │ └── ONNX Inference Engine (phishing-api / sicurre-ml — CamemBERTav2 INT8) │
   └───────────────────┬─────────────────────────────────────┬──────────────────┘
                       │                                     │
                       ▼                                     ▼
   ┌──────────────────────────────────────┐ ┌───────────────────────────────────┐
   │ Neon PostgreSQL (Prod Serverless DB) │ │ Grafana Alloy Observability Agent │
   │ ├── Schema 'sicurre' (Métier/Audit)  │ │ └── Export OTLP gRPC              │
   │ └── Schema 'auth' (Sessions/OAuth)   │ │     (Prometheus & Loki Logs)      │
   └──────────────────────────────────────┘ └───────────────────────────────────┘
```

### 3.1 Découpage des Repositories & Responsabilités Codebase

1. **Repository Main (`sicurre`) :**
   - **FastAPI Core (`src/data_platform/api/`) :** Ingestion des scans (`POST /v1/email/scan`), gestion des menaces (`/v1/threats`), quarantaine, feedbacks et connecteur Cloudflare (`/v1/integrations/cloudflare/*`).
   - **Better Auth Sidecar (`auth-service/`) :** Microservice Node.js/TypeScript autonome gérant les sessions utilisateurs, l'authentification multifacteur et les tokens OAuth.
   - **Services Métiers (`src/data_platform/services/`) :** Anonymisation PII, provisionnement Cloudflare, stockage des événements d'audit.
2. **Repository ML (`sicurre-ml`) :**
   - Pipeline de fine-tuning du modèle CamemBERTav2 sur dataset français de hameçonnage.
   - Exportation et quantification du modèle au format ONNX INT8 (`model_quantized.onnx`).
   - Têtes d'inférence CPU optimisées et scripts d'évaluation de la dérive des données (Model Drift).

---

## 4. Pipeline d'Inférence Multi-Étapes & Traitement Temps Réel

Chaque courriel soumis à la passerelle d'interception Sicurre traverse un pipeline de décision à 4 étapes exécuté séquentiellement :

```
   ┌──────────────────┐
   │ Inbound Email    │
   └─────────┬────────┘
             │
             ▼
┌──────────────────────────┐    Échoué (SPF/DKIM invalide)
│ Étape 1 : Filtres DNS    │ ───────────────────────────────┐
│ (SPF, DKIM, DMARC)       │                                │
└────────────┬─────────────┘                                │
             │ Reçu                                         │
             ▼                                              │
┌──────────────────────────┐                                │
│ Étape 2 : Reputation     │                                │
│ (Google Safe Browsing)   │                                │
└────────────┬─────────────┘                                │
             │ Reçu                                         │
             ▼                                              ▼
┌──────────────────────────┐                    ┌───────────────────────┐
│ Étape 3 : Classifier IA  │ ─────────────────> │ Verdict final :       │
│ (CamemBERTav2 ONNX INT8) │  Score Phishing    │ PHISHING / SPAM / SAFE│
└────────────┬─────────────┘                    └───────────┬───────────┘
             │ Si Phishing                                  │
             ▼                                              │
┌──────────────────────────┐                                │
│ Étape 4 : Explication    │                                │
│ (LLM gpt-4o-mini)        │ <──────────────────────────────┘
└──────────────────────────┘
```

1. **Étape 1 (Contrôle DNS Déterministe) :** Validation instantanée des enregistrements SPF, DKIM et DMARC de l'expéditeur via la bibliothèque `dnspython`. Rejet direct si le domaine expéditeur est forgé.
2. **Étape 2 (Vérification de Réputation Web) :** Analyse automatisée des URLs contenues dans le corps du message en interrogeant l'API Google Safe Browsing.
3. **Étape 3 (Classification par Réseau de Neurones ONNX) :** Exécution du modèle CamemBERTav2 quantifié INT8 sur le processeur de l'instance Hetzner. Temps d'inférence moyen : **12 millisecondes**.
4. **Étape 4 (Synthèse Explicative par LLM) :** En cas de détection de phishing, un appel asynchrone à un LLM léger (`gpt-4o-mini`) génère un résumé pédagogique de la menace en français à destination de l'utilisateur final.

---

## 5. Sécurité, Conformité RGPD & Isolation des Données

> [!IMPORTANT]
> **Garanties Complètes de Confidentialité RGPD (CNIL)**  
> Conformément aux réglementations européennes, Sicurre n'effectue **aucun stockage permanent du corps des emails**. Seules les métadonnées d'en-tête anonymisées sont conservées à des fins d'audit de sécurité.

### 5.1 Mesures de Sécurité Avancées Implémentées

| Vecteur de Menace | Mécanisme de Protection Implémenté | Fichier / Emplacement du Code |
|---|---|---|
| **Failles IDOR (Access Control)** | Filtre obligatoire `user_id` extrait de la session authentifiée sur chaque requête SQL relationnelle. | `src/data_platform/api/routers/threats.py` |
| **Fuite de Jetons OAuth** | Chiffrement symétrique fort AES-256-GCM des jetons de rafraîchissement avant écriture en BDD. | `src/core/security/crypto.py` |
| **Attaques par Déni de Service (DoS)** | Limitation de débit par adresse IP et par utilisateur via le middleware `slowapi`. | ADR-0009 / `src/data_platform/api/main.py` |
| **Exposition de Données PII** | Anonymisation systématique (`[EMAIL]`, `[PHONE]`, `[IBAN]`, `[URL]`) sur l'ensemble des logs d'audit. | `src/data_platform/cleaning/pii_redactor.py` |

---

## 6. Modèle Économique & Estimation des Coûts d'Infrastructure

### 6.1 Analyse du Coût de Revient Mensuel (Pour 100 TPE Client / 50 000 mails/mois)

| Composant d'Infrastructure | Fournisseur / Technologie | Dimensionnement & Usage | Coût Mensuel (€) |
|---|---|---|---|
| **Backend & Inférence ONNX** | Hetzner Cloud VPS (CX22) | 2 vCPU, 4 Go RAM, Ubuntu 24.04 | 4,50 € |
| **Ingestion Edge Intercept** | Cloudflare Email Routing & Workers | Free Tier (100k requêtes/mois) | 0,00 € |
| **Base de Données Serverless** | Neon PostgreSQL (Prod) | Compute réactif + 1 Go Storage | 0,00 € (Tier Gratuit) |
| **Gestion Authentification** | Better Auth Sidecar | Conteneur Node.js local sur Hetzner | 0,00 € (Inclus VPS) |
| **Télémétrie & Logs** | Grafana Alloy / Prometheus | Agent unifié local (OTLP gRPC) | 0,00 € (Self-hosted) |
| **Explications LLM (Optionnel)** | OpenAI API (`gpt-4o-mini`) | ~500 mails phishing expliqués | 0,25 € |
| **COÛT TOTAL OPÉRATIONNEL** | — | **50 000 courriels analysés** | **4,75 € / mois** |

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          ANALYSE DE RENTABILITÉ UNITAIRE                         │
├───────────────────────────────────────┬──────────────────────────────────────────┤
│ Tarif Abonnement SaaS Sicurre         │ 4,99 € / mois par domaine TPE            │
├───────────────────────────────────────┼──────────────────────────────────────────┤
│ Chiffre d'Affaires Mensuel (100 TPE)  │ 499,00 € / mois                          │
├───────────────────────────────────────┼──────────────────────────────────────────┤
│ Coût d'Infrastructure Mensuel Total   │ 4,75 € / mois                            │
├───────────────────────────────────────┼──────────────────────────────────────────┤
│ MARGE BRUTE OPÉRATIONNELLE            │ 99,04 % (Bénéfice : 494,25 € / mois)     │
└───────────────────────────────────────┴──────────────────────────────────────────┘
```

---

## 7. Modélisation des Données MERISE (MCD, MLD, MPD)

La base de données relationnelle Neon PostgreSQL s'appuie sur une modélisation MERISE rigoureuse validant la 3e Forme Normale (3NF) :

### 7.1 Modèle Conceptuel des Données (MCD)

```
┌─────────────────────────┐               ┌─────────────────────────┐
│       UTILISATEUR       │ 1,N       1,1 │     DOMAINE_PROTEGE     │
├─────────────────────────┤───────────────┼─────────────────────────┤
│ id_user (PK)            │ POSSÈDE       │ id_domain (PK)          │
│ email                   │               │ domain_name             │
│ password_hash           │               │ cloudflare_zone_id      │
│ created_at              │               │ status                  │
└─────────────────────────┘               └────────────┬────────────┘
                                                       │ 1,N
                                                       │
                                                       │ CONCERNE
                                                       │
                                                       │ 1,1
                                          ┌────────────▼────────────┐
                                          │    EVENEMENT_MENACE     │
                                          ├─────────────────────────┤
                                          │ id_threat (PK)          │
                                          │ sender_redacted         │
                                          │ subject_redacted        │
                                          │ threat_level            │
                                          │ confidence_score        │
                                          │ processed_at            │
                                          └─────────────────────────┘
```

---

## 8. Matrice de Correspondance avec les Compétences RNCP37827 (Bloc 3 / C14-C21)

| Compétence RNCP | Intitulé Officiel | Exigence de la Spécification & Preuve dans Sicurre |
|---|---|---|
| **C14** | Analyser les besoins applicatifs d'un client | Rédaction de la spécification fonctionnelle et analyse du marché TPE. |
| **C15** | Concevoir le cadre technique d'une application IA | Définition de l'architecture microservices (FastAPI, Cloudflare, Better Auth). |
| **C16** | Coordonner la mise en œuvre technique en Agile/MLOps | Mise en place de pipelines CI/CD, expérimentations DVC et suivi MLOps. |
| **C17** | Développer les composants et interfaces techniques | Implémentation du backend Python, du dashboard et des API REST typées. |
| **C18** | Automatiser les phases de tests du code source | Suite de tests unitaires et d'isolation IDOR automatisés via Pytest (`uv run pytest`). |
| **C19** | Créer un processus de livraison continue (CD) | Integration des GitHub Actions pour la validation automatisée des Pull Requests. |
| **C20** | Superviser une application IA (Monitoring/Logging) | Intégration de l'agent Grafana Alloy, suivi Prometheus et alertes de latence. |
| **C21** | Résoudre des incidents techniques applicatifs | Procédure documentée de traitement des fausses alertes et de reprise après panne. |

---

**Statut du Document :** Validé pour l'Homologation RNCP37827  
**Date d'Homologation :** 22 Juillet 2026  
**Auteur & Responsable Technique :** Adebayo Michael — Développeur IA  

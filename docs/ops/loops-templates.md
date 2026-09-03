# Loops.so Email Templates Specification - Sicurre

This document contains the exact copy, subject lines, preheaders, and template variables required to set up transactional and notification templates on Loops.so.

---

## 1. Email Confirmation (Post Sign-Up)
* **Loops Event / Transactional Name**: `email-verification`
* **Subject**: 🔒 Activez votre protection Sicurre en 2 secondes
* **Preheader (Preview Text)**: Confirmez votre adresse e-mail pour activer le bouclier anti-phishing.

### Copy Body:
```markdown
Bonjour {{firstName}},

Bienvenue chez Sicurre. Votre compte a été créé avec succès.

Pour finaliser votre inscription et activer la protection en temps réel sur votre boîte de messagerie, veuillez confirmer votre adresse e-mail en cliquant sur le bouton ci-dessous :

[Activer mon compte]({{verificationUrl}})

Si le bouton ne fonctionne pas, vous pouvez copier et coller ce lien dans votre navigateur :
{{verificationUrl}}

Ce lien de confirmation expirera dans 24 heures.

À très vite,
L'équipe Sicurre
```

---

## 2. Password Reset Request
* **Loops Event / Transactional Name**: `password-reset`
* **Subject**: 🔑 Réinitialisation de votre mot de passe Sicurre
* **Preheader (Preview Text)**: Suite à votre demande de réinitialisation de mot de passe.

### Copy Body:
```markdown
Bonjour {{firstName}},

Nous avons reçu une demande de réinitialisation de mot de passe pour votre compte Sicurre.

Si vous êtes à l'origine de cette demande, vous pouvez réinitialiser votre mot de passe en cliquant sur le lien ci-dessous :

[Réinitialiser mon mot de passe]({{resetUrl}})

Si vous n'avez pas demandé cette réinitialisation, vous pouvez ignorer cet e-mail en toute sécurité. Votre mot de passe actuel restera inchangé.

Ce lien de réinitialisation expirera dans 1 heure.

Sécurisez-vous bien,
L'équipe Sicurre
```

---

## 3. Threat Intercepted & Quarantined Alert
* **Loops Event / Transactional Name**: `threat-quarantined`
* **Subject**: ⚠️ Menace interceptée : Email suspect mis en quarantaine pour {{domainName}}
* **Preheader (Preview Text)**: Un email de phishing potentiel provenant de {{senderEmail}} a été intercepté.

### Copy Body:
```markdown
Bonjour {{firstName}},

Le bouclier Sicurre a détecté et intercepté un e-mail suspect ciblant votre domaine {{domainName}}. 

L'e-mail a été automatiquement dérouté et mis en quarantaine sécurisée pour protéger votre boîte de réception.

### Détails de la menace :
* **Expéditeur** : {{senderEmail}}
* **Objet** : {{emailSubject}}
* **Score de Risque** : {{riskScore}}% (Phishing)
* **Date d'interception** : {{interceptedAt}}

Vous pouvez inspecter cet e-mail en toute sécurité, le libérer s'il s'agit d'un faux positif, ou l'ajouter définitivement à la liste noire depuis votre espace client :

[Inspecter l'email en quarantaine]({{quarantineUrl}})

*Remarque : Les e-mails en quarantaine sont automatiquement purgés après 14 jours s'ils ne sont pas libérés.*

Restez vigilants,
Le système de sécurité Sicurre
```

---

## 4. DNS Security Protocol Alert (Policy Violations)
* **Loops Event / Transactional Name**: `dns-shield-alert`
* **Subject**: 🚨 Alerte Sécurité DNS : Configuration compromise pour {{domainName}}
* **Preheader (Preview Text)**: Vulnérabilité détectée. Votre réputation de messagerie risque d'être dégradée.

### Copy Body:
```markdown
Bonjour {{firstName}},

Notre audit automatique DNS a détecté une anomalie critique sur votre domaine {{domainName}}. Votre note de bouclier a chuté.

### Anomalies détectées :
{{dnsAnomalyDetails}}

**Pourquoi est-ce critique ?**
Sans ces protocoles DNS actifs (SPF, DKIM, DMARC), des usurpateurs peuvent facilement envoyer des e-mails en votre nom, dégradant gravement votre délivrabilité et la confiance de vos clients.

Veuillez vous rendre sur votre console d'administration pour récupérer les configurations requises et les ajouter à votre zone Cloudflare :

[Accéder au Bouclier de Domaine]({{domainShieldUrl}})

Besoin d'aide ? Notre support est à votre disposition.

L'équipe Sicurre
```

---

## 5. Account Lockdown Notification
* **Loops Event / Transactional Name**: `emergency-lockdown`
* **Subject**: 🚨 Verrouillage d'urgence activé sur votre passerelle
* **Preheader (Preview Text)**: Le bouclier Sicurre a été verrouillé pour bloquer toutes les liaisons entrantes.

### Copy Body:
```markdown
Bonjour {{firstName}},

Nous vous confirmons que le protocole de **Verrouillage d'urgence (Emergency Lockdown)** a été activé sur votre compte pour le domaine {{domainName}}.

**État actuel :**
- L'interception de tous les flux entrants non vérifiés est verrouillée.
- Les e-mails suspects sont rejetés ou mis en quarantaine immédiate sans prévisualisation.
- Les jetons d'API temporaires ont été révoqués.

Pour déverrouiller votre passerelle et restaurer l'état nominal de délivrabilité, veuillez vous connecter et désactiver le verrouillage depuis vos paramètres de sécurité :

[Ouvrir la Console de Sécurité]({{securityUrl}})

Si vous n'êtes pas à l'origine de cette action, veuillez contacter le support d'urgence Sicurre immédiatement.

L'équipe Sécurité Sicurre
```

---

## 6. Monthly Scan Quota Threshold Alert (80% / 100%)
* **Loops Event / Transactional Name**: `quota-warning`
* **Subject**: 📈 Quota d'emails analysés atteint à {{percentage}}% (Action requise)
* **Preheader (Preview Text)**: Vous approchez de la limite de votre forfait gratuit.

### Copy Body:
```markdown
Bonjour {{firstName}},

Vous avez consommé {{currentCount}} / {{maxQuota}} scans d'e-mails inclus ce mois-ci dans votre forfait gratuit (soit {{percentage}}%).

Pour éviter toute interruption de votre protection en temps réel, gardez un œil sur votre jauge ! Si la limite est atteinte, les nouveaux e-mails ne pourront plus être analysés contre le phishing jusqu'au mois prochain.

💡 Bonne nouvelle : Les forfaits premium arrivent bientôt pour vous permettre d'augmenter vos quotas.

Merci de votre confiance,
L'équipe Sicurre
```

# Incident supplémentaire — Télémétrie Grafana absente ou mélangée

## Constat

Les vues Grafana étaient vides ou mélangeaient Sicurre et Sicurre-ML. cAdvisor
produisait par ailleurs un volume important de diagnostics Docker sans valeur dans
Loki, alors que ses métriques restaient utiles.

## Causes identifiées

- droits lecture/écriture Grafana initialement confondus ;
- labels `stack`/`service_name` insuffisamment filtrés dans certaines vues ;
- deux collecteurs indépendants partageant les mêmes backends, perçus à tort comme
  un unique processus qui se remplaçait ;
- bruit cAdvisor envoyé dans Loki alors que Prometheus portait déjà sa santé.

## Corrections implémentées

- jetons lecture et écriture dédiés ;
- identités distinctes pour Sicurre et Sicurre-ML ;
- Alloy épinglé à une version testée ;
- cAdvisor conservé comme cible métrique et exclu du flux Loki Sicurre ;
- trois dashboards JSON séparés : runtime, infrastructure et pipeline télémétrique.

## Validation et preuve restante

Le contrôle du 17 juillet 2026 a obtenu HTTP 200 sur l'API de lecture Grafana et
les quatre cibles Sicurre (`sicurre-app`, `sicurre-host`,
`sicurre-containers`, `sicurre-alloy`) à `up=1`. Les trois dashboards Sicurre
versionnés étaient présents. La soumission finale doit encore inclure des
captures datées des dashboards et des requêtes Drilldown filtrées par `stack`.
La présence des JSON et la preuve API ne remplacent pas ces captures visuelles.

Le même contrôle a trouvé sept streams Loki Sicurre sur vingt-quatre heures pour
Alloy, Better Auth, l'API et le gateway, ainsi que deux traces Tempo récentes.
L'absence de logs applicatifs sur une fenêtre très courte sans trafic est normale
car les sondes et accès routiniers sont filtrés ; elle ne doit pas être confondue
avec une panne de collecte.

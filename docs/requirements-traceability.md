# Traçabilité du cahier des charges

Cette matrice confronte les exigences du sujet Workshop Bac+5 2026-27 au dépôt et
aux preuves effectivement disponibles. « Implémenté » ne signifie pas que le jury
ait encore vu une démonstration sur les deux PC. Les essais sur données synthétiques
ne sont pas présentés comme des performances de production.

| Exigence du sujet | Implémentation / preuve dans le dépôt | Reste à faire par le consortium |
|---|---|---|
| Paiement fictif par interface, API, authentification et base | Dashboard React, services FastAPI, jetons opérateur, PostgreSQL ; test du cycle métier dans `api/tests/test_incident_lifecycle.py` | Faire une transaction depuis le dashboard pendant la démonstration et expliquer le flux |
| Attaque contrôlée depuis une machine distincte | Script `redteam/attack.py`, jeton d'exercice séparé, injection limitée et expiration de sécurité | Configurer le point d'accès Windows `RESILIENCE-G<n>` ; exécuter depuis le PC Attaquant autorisé. Un essai localhost n'est pas une preuve de réseau à deux machines |
| Anomalie ML à partir de métriques du système | Isolation Forest sur métriques Prometheus ; données, variables, seuils et résultats synthétiques dans `ml-experiment.md` ; score transmis à l'API et affiché dans les événements | Rejouer et archiver les mesures sur les machines de remise ; discuter les limites des données synthétiques |
| Remédiation autonome et transaction post-reprise | Route AIOps à privilège dédié ; contrôle de santé, transaction métier, résultat de reprise ; test API du refus des autres identités | Vérifier les horodatages en direct et conserver les captures |
| Dashboard / supervision avant, pendant, après | Dashboard opérateur, métriques Prometheus, alertes, panneaux Grafana et événements Loki ; `ops/state` fournit la phase et la dernière décision ML | Vérifier les panneaux après déploiement et enregistrer le Clip Chrono |
| Consigne additionnelle : visage puis mot de passe, gestion des habilitations, caméra USB du PC Hôte, ESP8266 et LED bicolore | Service de reconnaissance OpenCV sur l'hôte, profils chiffrés, défi facial avant mot de passe, verrouillage après deux échecs, administration des comptes dans le dashboard et firmware PlatformIO piloté par MQTT | Installer l'agent sur le PC Hôte, enrôler les utilisateurs avec leur accord, configurer le Wi-Fi/câblage, calibrer LBPH et valider les états LED sur le matériel réel |
| Docker Compose reproductible | `docker-compose.yml`, `.env.example`, contrôles Compose documentés | Tester sur le PC Hôte propre et vérifier les ports et ressources réels |
| Ansible pour déploiement et restauration | `ansible/deploy.yml`, `ansible/restore.yml`, vérifications de santé et de cibles de scrape | Exécuter sur l'environnement de remise ; ajouter une sauvegarde/restauration PostgreSQL uniquement si le périmètre de reprise l'exige |
| Ollama et LangChain avec RAG documentaire local | Profil `ai`, modèle `llama3.2:3b`, index synchronisé et test d'index ; `ansible/enable-ai.yml` provisionne le modèle et l'assistant | Télécharger les modèles sur l'hôte, vérifier la santé et tester une question avec sources visibles ; prévoir la RAM/disque nécessaires |
| WAF, SIEM/SOC, durcissement et secrets SOPS | WAF OWASP CRS, Loki/Grafana, contrôles d'accès séparés, conteneur AIOps durci, `.sops.yaml` et fichier d'environnement chiffré dans le dépôt | Faire tourner toute clé Age ayant été commitée, chiffrer de nouveau les secrets, puis vérifier le déchiffrement sur l'hôte |
| EBIOS RM, PCA/PRA, NIS2/DORA et arbitrages | Analyse préliminaire dans `risk-pca-pra.md`, reliée à l'architecture et aux limites du prototype | Valider le BIA, les propriétaires, les scénarios, les niveaux de risque et les arbitrages avec le consortium/coach |
| Dossier PDF, présentation, Clip Chrono et Code.zip | Documentation source et générateur d'archive | Numéro d'équipe, identité/contribution nominative, dossier PDF final et présentation PPTX ; filmer un clip continu ≤60 s sur les deux PC et générer l'archive G<n> |

## Contrôle des critères locaux

- **Axe 1 (5 points)** : scénario localhost testé avec effet HTTP 503, décision ML,
  remédiation automatique et transaction post-reprise. La preuve depuis le second
  PC reste nécessaire pour satisfaire le dispositif demandé.
- **Axe 2 (4 points)** : les cinq domaines sont présents. Le RAG doit être démarré
  et montré le jour de la remise ; il n'est pas lancé par défaut afin d'éviter le
  téléchargement et le coût mémoire à chaque démarrage.
- **Axe 3 (4 points)** : les états sont visibles dans le dashboard et Grafana ; le
  Clip Chrono ne peut être remplacé par un test automatisé ou une vidéo fabriquée.
- **Axe 4 (4 points)** : les analyses sont préparées mais doivent être validées et
  défendues par l'équipe.
- **Axe 5 (3 points)** : la documentation de code est fournie ; contributions des
  personnes et rendus nominatifs nécessitent les informations réelles du groupe.

## État des secrets

Le fichier local `secrets/key.txt` a été retiré de l'index courant sans lire son
contenu. Le journal Git local montre qu'un fichier à ce chemin existe dans plusieurs
commits antérieurs. Si cette clé était une identité Age privée, il faut la révoquer
et ré-encrypter `secrets/app.enc.env` avant tout partage. La suppression dans le
dernier état et l'exclusion de l'archive ne retirent pas les données des anciens
commits ; toute purge de l'historique nécessite une coordination avec les personnes
qui possèdent des clones du dépôt.

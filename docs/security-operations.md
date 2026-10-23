# Sécurité et exploitation

## Secrets et comptes

- `.env`, les clés privées, les artefacts d’équipe et les dépendances ne font pas
  partie du dépôt source.
- Le fichier local `secrets/key.txt` était suivi par Git et a été retiré de l'index
  sans supprimer la copie de travail. Son contenu n’a pas été consulté. S'il contient
  une clé privée ou si elle a été partagée, la révoquer et la remplacer ; le retrait
  du dernier commit ne supprime pas les versions antérieures de l'historique.
- L’exemple `.env.example` ne contient que des marqueurs à remplacer. Utiliser des
  valeurs distinctes pour le mot de passe opérateur, le jeton de remédiation, la clé
  HMAC et le compte Grafana.
- Lorsqu’un secret SOPS est prévu, le déchiffrer localement sur le PC Hôte et ne
  transmettre ni la clé ni le contenu déchiffré. Renouveler tout secret déjà publié.
- Les mots de passe d’exercice sont des identifiants de démonstration, pas un mécanisme
  d’identité d’entreprise : aucune donnée réelle et aucune réutilisation de mot de passe.

## Réseau et privilèges

- Le réseau Compose sépare les services internes ; seuls le dashboard et le WAF ont
  un port publié.
- En mode attaquant, les ports hôte 80 et 8080 doivent être liés à l’interface du
  point d’accès Wi-Fi autorisé. Grafana et Prometheus restent liés à `127.0.0.1`.
- PostgreSQL, Loki, auth, API et AIOps n’ont pas de port publié.
- L’AIOps n’a plus le socket Docker et ne peut pas redémarrer arbitrairement l’hôte.
  Les autorisations applicatives sont séparées :

  | Identité | Routes permises | Routes refusées |
  |---|---|---|
  | Opérateur (Bearer) | Paiement, lecture de l'état métier | Injection et remédiation |
  | PC d'exercice (`EXERCISE_TOKEN`) | Injection de la panne de laboratoire | Remédiation, résultat de reprise |
  | AIOps (`REMEDIATION_TOKEN`) | Enregistrement d'une détection, remédiation contrôlée et résultat | Injection de panne, commandes système |

  Les événements métier enregistrent l'acteur, la décision, l'action et le résultat.
  L'injection est limitée à une panne active et expire après 180 secondes ; les
  nouvelles tentatives AIOps sont espacées. Les deux jetons sont distincts et ne
  doivent pas être partagés avec le PC Attaquant.
- Les conteneurs applicatifs API, auth et AIOps tournent avec un UID non privilégié.
- Le service d’authentification du prototype ne possède pas encore de limitation
  de débit, de MFA, de gestion du cycle de vie des comptes ni de verrouillage ; il
  doit rester sur le réseau isolé et ne constitue pas une offre d’identité de production.

## Limites à ne pas masquer

- La clé HMAC partagée facilite le prototype ; en production, préférer un émetteur
  d’identité établi, des clés rotatives avec vérification de rotation et une séparation
  cryptographique par service.
- Les secrets Compose sont transmis via variables d’environnement à partir d’un `.env`
  local. Cela évite le commit mais ne remplace pas un gestionnaire de secrets à l’exécution.
- Le point d’injection d’incident et le jeton d’exercice doivent être absents des
  environnements réels ; ne jamais activer cette configuration hors laboratoire.
- Les échanges du démonstrateur sont en HTTP, y compris les identifiants et jetons.
  Le réseau de laboratoire doit être isolé ; ne pas les transmettre sur un réseau
  non fiable. Un déploiement réel nécessiterait TLS et une gestion de secrets dédiée.
- Les journaux applicatifs partent vers Loki. La conservation, l’horodatage, les
  contrôles d’accès, les alertes et la rétention restent à calibrer selon la politique
  de l’organisation.
- L’application ne stocke que des données fictives et n’est pas un système de paiement
  de production.

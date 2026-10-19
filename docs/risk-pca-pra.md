# Analyse préliminaire des risques, continuité et conformité

> Document de travail du prototype. Il n’est pas une homologation, un avis juridique
> ni une analyse EBIOS RM complète. Les propriétaires métiers, le périmètre et les
> hypothèses doivent être validés par le consortium et le coach.

## Valeur métier et hypothèses

La valeur métier est la capacité à traiter et enregistrer des paiements fictifs
autorisés. Les actifs supports sont l’API, PostgreSQL, l’authentification, le WAF,
les secrets d’opérateur, les métriques et les journaux. Aucun client, compte ou
montant bancaire réel n’est dans le périmètre.

| Criticité préliminaire | Conséquence de l’indisponibilité ou de l’altération |
|---|---|
| Disponibilité des paiements | Transactions simulées retardées ou rejetées |
| Intégrité de la transaction | Montant, compte ou statut inexacts ; preuve métier invalide |
| Confidentialité des identifiants | Usurpation d’un opérateur et accès aux fonctions autorisées |
| Traçabilité et supervision | Impossible d’établir l’ordre des événements ou la reprise |

## Pré-analyse selon les ateliers EBIOS RM

| Atelier | Éléments de cadrage à discuter |
|---|---|
| 1. Cadrage et socle de sécurité | Limiter le système au réseau isolé, protéger les données fictives et le plan de remédiation ; préciser les dépendances et rôles du consortium. |
| 2. Sources de risque | Attaquant de laboratoire autorisé ; opérateur faisant une erreur ; défaillance logicielle, réseau ou de stockage. Les capacités, motivations et moyens sont à justifier par l’équipe. |
| 3. Scénarios stratégiques | Perturber le service de paiement ; réutiliser un secret d’opérateur ; modifier les données ou empêcher l’observation d’un incident. |
| 4. Scénarios opérationnels | Injection d’une panne contrôlée ; mot de passe de test divulgué ; API ou base indisponible ; scrape/promtail en échec ; remédiation mal configurée. |
| 5. Traitement | WAF et authentification ; secrets non versionnés ; réseau Compose interne ; observabilité ; validation métier post-reprise ; revue humaine des actions de production. |

### Registre de risques préliminaire

| Risque | Impact | Mesures dans le prototype | Risque résiduel / preuve à collecter |
|---|---|---|---|
| Saturation ou interruption de l’API | Paiements indisponibles | Injection contrôlée, détection métrique ML, retour au nominal | Mesurer délai et faux positifs sur plusieurs essais ; le scénario ne couvre pas une panne physique complète. |
| Identifiants ou jeton divulgués | Paiements non autorisés / remédiation abusée | Jeton opérateur court, secret de remédiation distinct, `.env` exclu | Pas de coffre central ni rotation automatisée ; rotation à tester et capture du secret interdite. |
| Perte ou altération de PostgreSQL | Perte d’intégrité et de preuve | État persistant en volume et vérification métier | Pas de sauvegarde/restauration PITR validée ; restaurer une sauvegarde est un essai restant. |
| Détection erronée ou Prometheus indisponible | Action tardive ou absence de reprise | Modèle Isolation Forest, minimum d’évidence et erreurs de collecte signalées | Données d’entraînement synthétiques ; mesurer précision/rappel et temps de détection sur un jeu d’essais plus large. |
| Privilège excessif du remédiateur | Propagation de compromission à l’hôte | Pas d’accès au socket Docker ; endpoint interne limité par jeton | La confiance entre services repose sur des secrets partagés ; envisager identité de service et secrets rotatifs en production. |
| Exposition accidentelle sur le réseau | Attaque hors périmètre | Ports de gestion liés à localhost ; interface de laboratoire explicitement choisie | Vérifier `docker compose ps`, pare-feu et règles de point d’accès avant chaque démo. |

Les niveaux de gravité/probabilité, propriétaires, menaces et objectifs métiers
doivent être attribués par le consortium, avec une matrice de risque et des décisions
documentées. Aucun score EBIOS n’est inventé ici.

## PCA/PRA proposé pour le prototype

- **Périmètre** : dashboard, auth, API, PostgreSQL, Prometheus, Loki et AIOps.
- **RTO cible du scénario contrôlé** : retour métier nominal en moins de 90 secondes
  (contrainte du script, non mesurée tant que les essais ne sont pas exécutés).
- **RPO cible de la panne injectée** : zéro transaction validée perdue, car le défaut
  rejette les appels avant écriture. Ce n’est pas un RPO garanti pour perte de volume.
- **Détection** : les métriques Prometheus et événements Loki alimentent l’analyse ;
  une interruption du monitoring est traitée comme un défaut de télémétrie à investiguer,
  pas comme une preuve d’incident métier.
- **Reprise** : action bornée qui retire le défaut injecté ; vérification API puis
  transaction de contrôle ; statut déclaré « rétabli » seulement après réussite.
- **Données** : volume PostgreSQL persistant dans Compose ; sauvegarde, restauration,
  test de cohérence, rétention et clés de chiffrement sont des travaux à valider.
- **Responsabilités** : opérateur consigne l’incident et vérifie l’exercice ; AIOps
  exécute uniquement la remédiation autorisée ; l’assistant local conseille sans agir.
- **Repli** : à défaut de remédiation sous 90 secondes, arrêter la démonstration,
  conserver les logs et utiliser la procédure supervisée ; ne pas masquer une action manuelle.

## NIS2 / DORA : analyse de périmètre, pas déclaration de conformité

Le scénario pédagogique emploie un opérateur financier fictif. L’applicabilité
réglementaire réelle dépend du statut juridique, du pays, des services et des entités
concernés ; elle n’est pas établie par ce prototype.

- **Sujets à rapprocher des exigences NIS2** : gouvernance du risque, gestion des
  incidents, continuité et sauvegarde, sécurité de la chaîne d’approvisionnement,
  contrôle d’accès, formation, journalisation et notification. Le prototype montre
  une petite chaîne technique observable, mais pas la gouvernance ni les délais de
  notification d’une organisation réelle.
- **Sujets à rapprocher de DORA** : gestion du risque TIC, détection et réponse aux
  incidents, continuité/récupération, tests de résilience et gestion des tiers TIC.
  Un test unique en laboratoire ne couvre ni les obligations de reporting, ni les
  tests avancés, ni les registres ou contrôles d’un établissement financier.
- **Recommandations de conseil** : faire confirmer l’applicabilité par le juridique
  et le RSSI ; établir le BIA et les services critiques ; définir des RTO/RPO approuvés ;
  formaliser les sauvegardes/restaurations ; inventorier les tiers ; répéter les exercices
  et archiver les preuves ; contrôler l’accès et la rotation des secrets.

Avant le jury, ajouter des résultats effectivement mesurés, les arbitrages du groupe,
les propriétaires des risques, la contribution de chaque personne et les limites
restantes. Ne présenter aucune ligne « cible » comme une preuve observée.

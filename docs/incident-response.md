# Procédure opérateur et preuves de reprise

## Préconditions

- Utiliser seulement le réseau de laboratoire du consortium et le PC Attaquant autorisé.
- Le PC Hôte doit disposer d’un `.env` local valide et non versionné.
- Vérifier `docker compose ps`, la connexion au dashboard, la santé nominale et
  l’existence d’une transaction de contrôle réussie.
- Ouvrir le dashboard, Grafana et les logs AIOps sur le PC Hôte avant l’enregistrement.
- Ne jamais exécuter le scénario contre un réseau du campus, un autre groupe ou Internet.

## Séquence démontrable

1. **Avant** : l’API est opérationnelle, le dashboard affiche l’état nominal ; une
   transaction de faible montant est acceptée et visible dans PostgreSQL.
2. **Injection autorisée** : lancer `python redteam\attack.py` sur le PC Attaquant.
   Le script appelle `POST /admin/inject-fault` avec le jeton d’exercice.
3. **Effet observable** : les paiements de test reçoivent HTTP 503 ; aucun échec n’est
   comptabilisé comme transaction validée. Les métriques et logs sont collectés.
4. **Détection** : l’AIOps affiche les caractéristiques observées et la décision
   Isolation Forest dans ses logs ; un défaut de scrape n’entraîne pas de reprise
   automatique.
5. **Réponse** : l’AIOps utilise son jeton limité pour retirer la panne contrôlée.
   Il n’exécute aucun redémarrage Docker.
6. **Vérification** : AIOps confirme `/health`, enregistre la transaction synthétique
   `AIOPS-RECOVERY-CHECK` et rend visible le statut de reprise.
7. **Après** : le script exige ensuite une nouvelle transaction Red Team réussie.
   L’équipe vérifie le journal, Grafana, la présence des transactions en base et
   l’absence d’une panne active.

En cas d’absence de retour au nominal dans les 90 secondes, le script échoue
explicitement. Consulter `docker compose logs aiops-detector payment-api prometheus`
et Grafana. L’injection expire au bout de trois minutes ; ne pas présenter un
redémarrage manuel comme une reprise autonome.

## Critères d’acceptation mesurables

- 8 paiements d’exercice sont émis ; au moins un reçoit 503 pendant l’incident.
- Les métriques Prometheus montrent un ratio d’échecs anormal dans la fenêtre de
  60 secondes, et le journal AIOps indique la prédiction et les caractéristiques.
- Le log de remédiation suit la détection sans commande corrective humaine.
- La santé passe à `ok`, une transaction de vérification AIOps est validée et une
  nouvelle transaction Red Team réussit.
- Les IDs de transactions, événements d’incident et horaires concordent dans le
  dashboard, Grafana/Loki et PostgreSQL.

Consigner les horaires observés et les résultats réels avant d’inscrire un RTO
mesuré dans le dossier de gouvernance. Les valeurs cibles de [`risk-pca-pra.md`](./risk-pca-pra.md)
ne sont pas des résultats de test.

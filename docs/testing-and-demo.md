# Tests, preuves et démonstration

## Tests automatisés

`api/tests/test_incident_lifecycle.py` vérifie l’authentification, l’interdiction
d’injecter sans jeton, l’échec 503 pendant l’incident, le chemin de remédiation, la
création d’une transaction après reprise et l’état consolidé du dashboard.
`aiops/test_detector.py` vérifie que l’Isolation Forest classe des observations
nominales comme normales et un vecteur d’échecs extrême comme anomalie.
Le jeu synthétique séparé mesure aussi les taux de faux positifs et faux négatifs,
avec une limite de 5 % pour chacun ; voir [`ml-experiment.md`](./ml-experiment.md)
pour les distributions et les limites de cette mesure.
Les tests vérifient également que les prédictions seules ou les métriques seules ne
suffisent pas à déclencher une action, et que la décision transmise à l'API interne
contient le score et les caractéristiques observées.
Il vérifie également qu’une reprise déjà confirmée n’est pas relancée tant que
les compteurs de la fenêtre Prometheus restent élevés ; en cas d’échec de reprise,
une nouvelle tentative est espacée par le délai de refroidissement.
Le dashboard Grafana provisionné présente les métriques d’incident, l’anomalie ML,
la transaction de reprise vérifiée, les alertes Prometheus et les événements Loki.
Le dashboard opérateur affiche aussi l’étape courante de la reprise.

Exécuter :

```powershell
py -3.12 -m pip install -r api\requirements.txt -r api\requirements-dev.txt
py -3.12 -m pip install -r aiops\requirements.txt
py -3.12 -m pytest api\tests aiops\test_detector.py -q
Set-Location ..\dashboard
npm ci
npm run build
```

Les tests automatisés emploient une base SQLite temporaire. Ils ne valident pas les
images Docker, le WAF, Prometheus, Loki, les flux réseau Windows, la durée réelle de
reprise ni le comportement avec une base de données restaurée.
Le workflow `.github/workflows/ci.yml` rejoue les tests API/AIOps, construit le
dashboard et vérifie la génération d'une archive expurgée des secrets sur chaque
push et pull request. Ce contrôle CI n'est pas une preuve de déploiement ni une
recette de bout en bout.

## Recette à exécuter et consigner sur le PC Hôte

1. `docker compose --env-file .env config --quiet`
2. `docker compose --env-file .env up --build -d`
3. `docker compose ps` : vérifier les services sains et l’absence de port API/DB publié.
4. Sur le PC Hôte, créer et consigner une transaction fictive réussie depuis le dashboard.
5. Depuis le PC Attaquant autorisé, exécuter le script du README.
6. Capturer en continu les états nominal, incident, prédiction ML, remédiation et
   paiement après reprise ; le script d'exercice et les événements métier portent
   des horodatages.
7. Vérifier dans Grafana les métriques Prometheus et les journaux Loki.
8. Vérifier dans PostgreSQL les montants fictifs et l’état des transactions.
9. Répéter les essais avec Prometheus indisponible, mot de passe invalide, WAF
   actif et délai d’API. Consigner les échecs ; ne pas inventer de résultats.
10. Sur une machine disposant des ressources nécessaires, exécuter
    `ansible-playbook -i ansible/inventory.ini ansible/enable-ai.yml`, puis tester
    l’assistant depuis le dashboard : poser une question couverte par une procédure
    et vérifier que les sources Markdown sont affichées.

Le build Docker et l’essai réseau ne peuvent être déclarés réussis tant que Docker
Desktop et le PC Attaquant ne sont pas disponibles. Une absence de démon Docker est
un blocage d’environnement, pas un résultat positif.

## Preuve locale déjà observée

Lors de l'essai contrôlé exécuté le 20 octobre 2026 sur `localhost`, une transaction
fictive nominale a réussi avant l'incident (`TXN-3-567`, 0,03 €). Le scénario a
provoqué huit réponses HTTP 503. L'API a consigné l'injection à
`2026-10-20T20:21:17.010Z`, la remédiation AIOps à `20:21:22.912Z`, puis la
vérification métier à `20:21:23.108Z` (`TXN-4-397`, 0,01 €). La transaction après
reprise `TXN-5-148` a réussi. Le temps injection → vérification observé était
d'environ **6,1 secondes** ; il s'agit d'un seul essai local, pas d'un RTO garanti.
Les deux cycles locaux ont laissé cinq transactions fictives validées pour un total
de 0,09 €, cohérent avec l'état métier interrogé.

Cette preuve est antérieure à la recette depuis un second PC ; elle ne remplace pas
la capture vidéo continue ni la répétition sur le point d'accès Windows du consortium.

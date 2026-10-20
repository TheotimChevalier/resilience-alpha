# Tests, preuves et démonstration

## Tests automatisés

`api/tests/test_incident_lifecycle.py` vérifie l’authentification, l’interdiction
d’injecter sans jeton, l’échec 503 pendant l’incident, le chemin de remédiation, la
création d’une transaction après reprise et l’état consolidé du dashboard.
`aiops/test_detector.py` vérifie que l’Isolation Forest classe des observations
nominales comme normales et un vecteur d’échecs extrême comme anomalie.
Il vérifie également qu’une reprise déjà confirmée n’est pas relancée tant que
les compteurs de la fenêtre Prometheus restent élevés ; en cas d’échec de reprise,
une nouvelle tentative est espacée par le délai de refroidissement.

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
4. Sur le PC Hôte, créer une transaction fictive depuis le dashboard.
5. Depuis le PC Attaquant autorisé, exécuter le script du README.
6. Capturer en continu les états nominal, incident, prédiction, remédiation et
   paiement après reprise ; horodater les étapes.
7. Vérifier dans Grafana les métriques Prometheus et les journaux Loki.
8. Vérifier dans PostgreSQL les montants fictifs et l’état des transactions.
9. Répéter les essais avec Prometheus indisponible, mot de passe invalide, WAF
   actif et délai d’API. Consigner les échecs ; ne pas inventer de résultats.

Le build Docker et l’essai réseau ne peuvent être déclarés réussis tant que Docker
Desktop et le PC Attaquant ne sont pas disponibles. Une absence de démon Docker est
un blocage d’environnement, pas un résultat positif.

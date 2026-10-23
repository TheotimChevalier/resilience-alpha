# Expérience ML reproductible

## Modèle et objectif

Le détecteur utilise `sklearn.ensemble.IsolationForest`, ajusté au démarrage sur
800 observations synthétiques nominales. La génération déterministe est codée dans
`aiops/detector.py` avec la graine 42 ; aucun historique de production n'est utilisé
ni conservé. Le modèle est réentraîné à chaque démarrage du conteneur.

Les trois variables, dans l'ordre, sont :

1. nombre total de requêtes de paiement observé sur la fenêtre Prometheus de 60 s ;
2. proportion des réponses HTTP 5xx parmi ces requêtes ;
3. latence moyenne des paiements, en secondes.

La base synthétique utilise un volume Poisson de paramètre 3, une proportion d'erreur
Beta(0,6 ; 35) et une latence normale de moyenne 0,1 s et d'écart-type 0,025 s,
bornée entre 0,025 et 0,25 s. Les fenêtres sans trafic ont une proportion d'erreur
et une latence à zéro. L'Isolation Forest est configuré avec `contamination=0.01`
et `random_state=42`.

## Évaluation synthétique

`generate_evaluation_data()` produit un jeu déterministe séparé de 400 observations
nominales et 200 incidents étiquetés. Les incidents synthétiques combinent un volume
Poisson de paramètre 10, une proportion d'erreur Beta(10 ; 2) et une latence normale
de moyenne 0,12 s et d'écart-type 0,025 s, bornée entre 0,025 et 0,25 s. La latence
incidente reste donc dans la plage nominale : la détection s'appuie sur le volume
et le ratio 5xx, comme dans le scénario contrôlé. La graine est 2026.

Le test `test_synthetic_evaluation_measures_false_positives_and_false_negatives`
calcule les taux de faux positifs (nominal prédit anomalie) et de faux négatifs
(incident prédit nominal) et impose chacun à 5 % au maximum sur ce jeu. Avec les
paramètres ci-dessus, le résultat déterministe est de 16 faux positifs sur 400
observations nominales (4 %) et 0 faux négatif sur 200 incidents (0 %). Ce résultat
est une mesure reproductible sur données artificielles, pas une estimation des
performances sur trafic réel.

## Lien avec la remédiation et limites

Une prédiction Isolation Forest seule ne déclenche pas l'action. L'AIOps exige aussi
au moins trois requêtes et un ratio 5xx d'au moins 25 %. Si les deux conditions sont
réunies, il consigne le score et les caractéristiques, puis appelle l'API interne
avec son jeton dédié. L'API journalise la décision dans le flux d'événements du
dashboard et dans Loki avant d'autoriser la remédiation. Le détecteur n'exécute
aucune commande Docker et ne choisit aucune action arbitraire.

Ce modèle pédagogique n'est pas entraîné sur des étiquettes ou des données
représentatives. Les distributions synthétiques, les paramètres et le seuil
d'évidence sont des hypothèses de démonstration ; ils doivent être recalibrés et
évalués sur des données autorisées avant tout usage réel.

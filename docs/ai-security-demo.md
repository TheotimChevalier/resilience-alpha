# Démonstration de la protection IA locale

## Démarrage

Ollama doit tourner sur le PC hôte et le modèle doit être présent :

```powershell
ollama list
ollama run llama3.2:latest
```

Le service `payment-api` contacte Ollama via
`http://host.docker.internal:11434`. L'API expose son état sur
`http://localhost:8000/security/status`.

## Parcours devant le jury

1. Ouvrir le dashboard sur `http://localhost:8080` et vérifier qu'Ollama est indiqué
   comme connecté.
2. Cliquer **Simuler un signal d'attaque**. Cette action n'envoie qu'une requête
   synthétique locale ; elle ne génère aucune rafale de trafic.
3. La garde Python applique immédiatement les limites obligatoires. Les signaux
   suspects sont envoyés en tâche de fond au modèle Ollama local, qui renvoie aussi
   une recommandation `BLOCK`/`ALLOW`, une catégorie de risque et une explication en
   français. Le dashboard distingue la recommandation IA de l'action appliquée par
   Python. L'IA ne reçoit aucun identifiant ni secret et ne peut exécuter aucune
   commande ; elle ne peut pas annuler une limite de sécurité obligatoire.
4. Effectuer un paiement de montant normal pour montrer que le service reste
   disponible après le blocage.

Le scénario automatisé équivalent est :

```powershell
python redteam\attack.py
```

## Vérifications et observabilité

- Santé de l'API : `http://localhost:8000/health`
- Événements de protection : `http://localhost:8000/security/events`
- Prometheus : requête `payment_ai_guard_blocked_total`
- Prometheus : requête `up{job="payment-api"}` (résultat attendu : `1`)
- Grafana Explore, source Loki : `{app="payment-api", level="critical"}`
- Grafana Explore, logs de paiement : `{app="payment-api"}`

La politique de protection est en défense en profondeur : Python refuse le marqueur
de simulation, les montants supérieurs à 5 000 EUR et les montants nuls ou négatifs
avant toute écriture en base ; Ollama recommande également une décision et explique
chaque signal. Python conserve l'autorité d'exécution pour qu'une sortie de modèle
erronée ne puisse pas autoriser un paiement interdit. Si Ollama est indisponible,
la règle Python continue de bloquer et le statut de repli est journalisé.

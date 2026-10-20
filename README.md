# Resilience Alpha

Démonstrateur local de paiement fictif et de cyber-résilience. Toutes les données et
tous les scénarios sont synthétiques ; ne pas utiliser de données bancaires réelles.

## Démarrage local

Prérequis : Docker Desktop avec Compose v2, Python 3.12 pour les tests et scripts,
et un réseau de laboratoire autorisé. Le front est servi sur le port 8080 et le WAF
sur le port 80. PostgreSQL, l’API, l’authentification, Prometheus, Loki et AIOps ne
sont pas publiés directement sur l’hôte.

1. Créer la configuration locale non versionnée :

   ```powershell
   Copy-Item .env.example .env
   ```

2. Remplacer chaque valeur `replace-with-...` par une valeur unique et robuste.
   Exemple pour créer une valeur aléatoire sans l’afficher dans les logs :

   ```powershell
   py -3.12 -c "import secrets; print(secrets.token_hex(32))"
   ```

   Garder `.env` hors du dépôt et de toute archive. Si l’équipe utilise SOPS,
   déchiffrer son fichier d’environnement protégé vers `.env` sur le PC Hôte et
   vérifier les noms des variables avant le démarrage. La clé Age doit être conservée
   hors du workspace, par exemple dans le profil utilisateur de l’opérateur.
   Ne jamais archiver une clé privée avec le code.

3. Vérifier la configuration puis démarrer le cœur :

   ```powershell
   docker compose --env-file .env config --quiet
   docker compose --env-file .env up --build -d
   ```

4. Ouvrir `http://localhost:8080`. Les valeurs d’accès opérateur viennent de
   `OPERATOR_USERNAME` et `OPERATOR_PASSWORD` dans `.env`.

Par défaut, les ports publiés sont limités à `127.0.0.1`. Pour la démonstration
avec un PC Attaquant distinct, régler `WAF_BIND_ADDRESS` et `DASHBOARD_BIND_ADDRESS`
sur l’adresse de l’interface du point d’accès de laboratoire du PC Hôte (par exemple
`192.168.137.1`). Ne pas exposer le démonstrateur à un réseau tiers. Une fois la
configuration changée, vérifier les ports réellement publiés avec
`docker compose ps`. Si un port local est déjà utilisé, `DASHBOARD_PORT` permet de
choisir un autre port hôte (la valeur `18081` est utilisée dans l’environnement
de développement actuel car `8080` est occupé par un autre projet).

## Scénario de résilience contrôlé

Sur le PC Attaquant, installer les dépendances et fournir les identifiants de test et le
jeton de remédiation par variables d’environnement. Ces valeurs doivent correspondre
au `.env` local du PC Hôte et ne doivent jamais être ajoutées à un script versionné.

```powershell
$env:TARGET_HOST = "192.168.137.1"
$env:OPERATOR_USERNAME = "operator"
$env:OPERATOR_PASSWORD = "<mot-de-passe-local>"
$env:REMEDIATION_TOKEN = "<jeton-local>"
py -3.12 -m pip install -r redteam\requirements.txt
py -3.12 redteam\attack.py
```

Le script utilise uniquement le point d’accès du laboratoire : il authentifie
l’opérateur, injecte une panne applicative contrôlée, émet des transactions fictives
qui doivent échouer en HTTP 503, puis attend la détection ML et la reprise automatique.
L’AIOps supprime le drapeau de panne, vérifie `/health`, crée une transaction de contrôle
de 0,01 € et publie le résultat. Le script exige ensuite une transaction fictive réussie
après la reprise. L’incident expire également après trois minutes si la chaîne de
remédiation ne fonctionne pas.

Pour suivre les composants :

- Dashboard : `http://localhost:8080`
- Grafana : `http://localhost:3000` (lié à la boucle locale uniquement)
- Prometheus : `http://localhost:9090` (lié à la boucle locale uniquement)
- Logs AIOps : `docker compose logs -f aiops-detector`
- État de la pile : `docker compose ps`

## Assistant RAG local (facultatif)

L’assistant est un profil facultatif pour éviter de télécharger un modèle local de
plusieurs gigaoctets lors du démarrage normal. Il utilise le modèle compact
`llama3.2:3b` (moins de 8 milliards de paramètres) et l’index documentaire local.

```powershell
docker compose --env-file .env --profile ai up -d ollama
docker compose --env-file .env exec ollama ollama pull llama3.2:3b
docker compose --env-file .env exec ollama ollama pull nomic-embed-text
docker compose --env-file .env --profile ai up --build -d rag-assistant
```

L’onglet Assistant du dashboard nécessite une session opérateur et les conteneurs
du profil `ai`. Il ne possède aucun droit de remédiation.

## Tests

Les instructions de tests et les limites des résultats sont dans
[`docs/testing-and-demo.md`](./docs/testing-and-demo.md). En local :

```powershell
py -3.12 -m pip install -r api\requirements.txt -r api\requirements-dev.txt
py -3.12 -m pip install -r aiops\requirements.txt
py -3.12 -m pytest api\tests aiops\test_detector.py -q
Set-Location dashboard
npm ci
npm run build
```

Le test complet de bout en bout nécessite Docker Desktop actif, un compte de test
local et les deux machines du réseau de laboratoire.
Les tests API/AIOps et le build du dashboard sont également exécutés par GitHub
Actions à chaque push et pull request ; ils ne remplacent pas la recette réelle sur
les deux machines.

## Documentation et livrables

- Architecture et flux : [`docs/architecture.md`](./docs/architecture.md)
- Reprise et limites : [`docs/incident-response.md`](./docs/incident-response.md)
- EBIOS RM, PCA/PRA, NIS2/DORA : [`docs/risk-pca-pra.md`](./docs/risk-pca-pra.md)
- Mesures de sécurité : [`docs/security-operations.md`](./docs/security-operations.md)
- Vérifications et démonstration : [`docs/testing-and-demo.md`](./docs/testing-and-demo.md)
- Dossier, présentation et vidéo exigés : [`docs/deliverables.md`](./docs/deliverables.md)

Créer une archive de code expurgée des secrets avec :

```powershell
py -3.12 scripts\package_release.py --team 5
```

Remplacer `5` par le numéro réel de votre équipe. Le script refuse d’archiver les
secrets, `.env`, clés privées, dépendances installées et sorties de build. Les
contributions nominatives, le dossier PDF
final, la présentation et le Clip Chrono doivent être complétés par le consortium.

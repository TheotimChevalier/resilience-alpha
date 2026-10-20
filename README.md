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
   Le `EXERCISE_TOKEN` doit être distinct du `REMEDIATION_TOKEN`. Si un `.env`
   existant ne contient pas encore `EXERCISE_TOKEN`, l'ajouter avant de lancer Compose.
   Exemple pour créer une valeur aléatoire sans l’afficher dans les logs :

   ```powershell
   py -3.12 -c "import secrets; print(secrets.token_hex(32))"
   ```

   Si une valeur manque dans le fichier issu de SOPS, la créer localement sans
   l'afficher dans le terminal :

   ```powershell
   $exerciseToken = py -3.12 -c "import secrets; print(secrets.token_hex(32))"
   Add-Content -Path .env -Value "EXERCISE_TOKEN=$exerciseToken"
   Remove-Variable exerciseToken
   ```

   Garder `.env` hors du dépôt et de toute archive. Pour utiliser SOPS, installer
   SOPS et Age sur le PC Hôte, garder la clé privée Age hors du workspace, puis
   déchiffrer localement le fichier chiffré vers `.env` :

   ```powershell
   sops --decrypt --input-type dotenv --output .env secrets\app.enc.env
   ```

   Vérifier que le `.env` généré contient `EXERCISE_TOKEN` distinct de
   `REMEDIATION_TOKEN`. Ne jamais archiver une clé privée ni le `.env`.

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

Sur le PC Attaquant, installer les dépendances et fournir les identifiants de test et
le jeton d'exercice par variables d’environnement. Le jeton d'exercice doit être
distinct du `REMEDIATION_TOKEN`, qui reste uniquement sur le PC Hôte et dans les
conteneurs autorisés.

```powershell
$env:TARGET_HOST = "192.168.137.1"
$env:OPERATOR_USERNAME = "operator"
$env:OPERATOR_PASSWORD = "<mot-de-passe-local>"
$env:EXERCISE_TOKEN = "<jeton-exercice-local>"
py -3.12 -m pip install -r redteam\requirements.txt
py -3.12 redteam\attack.py
```

Le script utilise uniquement le point d’accès du laboratoire : il authentifie
l’opérateur, injecte une panne applicative contrôlée, émet huit paiements fictifs
dont au moins un doit échouer en HTTP 503, puis attend la détection ML et la reprise
automatique. Les paiements envoyés après la reprise peuvent réussir.
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

## Assistant RAG local (composant requis, démarrage séparé)

L’assistant fait partie du périmètre fonctionnel demandé. Il est placé dans le profil
Compose `ai` pour éviter de télécharger plusieurs gigaoctets et de consommer la RAM
de l’hôte à chaque démarrage de la plateforme. Il utilise Ollama, LangChain, Chroma,
le modèle compact `llama3.2:3b` (3 milliards de paramètres) et un modèle d’embeddings
local.

```powershell
ansible-playbook -i ansible/inventory.ini ansible/enable-ai.yml
```

Le playbook télécharge les modèles, construit l’assistant, attend son état de santé
et vérifie qu’il est prêt. L’index est synchronisé depuis les fichiers Markdown
montés en lecture seule. L’onglet Assistant nécessite une session opérateur ; il
fournit les sources des réponses et ne possède aucun droit de remédiation.
Prévoir plusieurs gigaoctets de stockage et de RAM pour Ollama et les modèles.

## Ansible

Depuis le PC Hôte (ou un contrôleur disposant d'Ansible et d'un accès local au
moteur Docker), lancer le déploiement et la vérification :

```bash
ansible-playbook -i ansible/inventory.ini ansible/deploy.yml
```

Après un arrêt ou une dégradation de la pile, réappliquer l'état Compose sans
supprimer le volume PostgreSQL :

```bash
ansible-playbook -i ansible/inventory.ini ansible/restore.yml
```

Les playbooks valident la configuration, attendent les contrôles de santé et
vérifient les points d'accès internes. Ils restaurent l'état déclaré dans le checkout
courant ; ils ne restaurent pas une sauvegarde de données et ne reviennent pas à une
ancienne version du code.

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

Les tests de synchronisation documentaire RAG s'exécutent dans un environnement
Python séparé pour éviter les conflits de dépendances avec scikit-learn :

```powershell
py -3.12 -m venv .venv-rag
.\.venv-rag\Scripts\python.exe -m pip install -r rag\requirements.txt -r rag\requirements-dev.txt
.\.venv-rag\Scripts\python.exe -m pytest rag\test_indexing.py -q
```

Le test complet de bout en bout nécessite Docker Desktop actif, un compte de test
local et les deux machines du réseau de laboratoire.
Les tests API/AIOps et le build du dashboard sont également exécutés par GitHub
Actions à chaque push et pull request ; ils ne remplacent pas la recette réelle sur
les deux machines.

## Documentation et livrables

- Architecture et flux : [`docs/architecture.md`](./docs/architecture.md)
- Correspondance avec le sujet et travaux de remise : [`docs/requirements-traceability.md`](./docs/requirements-traceability.md)
- Expérience ML synthétique et mesures : [`docs/ml-experiment.md`](./docs/ml-experiment.md)
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

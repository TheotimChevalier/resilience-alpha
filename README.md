# Resilience Alpha

Démonstrateur local de paiement fictif et de cyber-résilience. Toutes les données et
tous les scénarios sont synthétiques ; ne pas utiliser de données bancaires réelles.

Le dossier technique du projet, incluant le schéma d’architecture, est disponible
dans [resilience-alpha-documentation.pdf](./resilience-alpha-documentation.pdf).

## ESP8266 et LED bicolore

Le projet PlatformIO est dans `firmware\`. L'ESP8266 se branche en USB au PC Hôte
(port série COM3 par défaut) ; aucun Wi-Fi, mot de passe MQTT ni fichier de secrets
n'est requis. Le modèle de carte est NodeMCU ESP8266 ; d'après le câblage actuel,
la LED verte utilise D1 et la rouge D2, chacune avec une résistance série de 220 Ω,
et leur retour commun est relié à G (GND). Adapter les broches au câblage réel avant
la mise sous tension.

Construire et téléverser l'environnement `esp8266` avec PlatformIO, puis démarrer
l'agent caméra sur le PC Hôte : il relaie les états d'authentification vers la carte
par le même câble USB série. Ne pas lancer de moniteur série pendant que l'agent
utilise la carte. Les états pilotés sont : vert clignotant pendant l'attente du mot
de passe, vert fixe pendant 30 s après succès, rouge fixe pendant 30 s après visage
non reconnu, et dix impulsions rouges après mot de passe incorrect.

Les détails d'installation, le fonctionnement des verrouillages et les limites du
prototype de reconnaissance sont décrits dans
[`docs/face-auth-and-iot.md`](./docs/face-auth-and-iot.md).

## Démarrage local

Prérequis : Docker Desktop avec Compose v2, Python 3.12 pour les tests et scripts,
et un réseau de laboratoire autorisé. Le front est servi sur le port 8080 et le WAF
sur le port 80. PostgreSQL, l’API, l’authentification, Prometheus, Loki et AIOps ne
sont pas publiés directement sur l’hôte. Seul l'agent du PC Hôte écoute sur le port
TCP 8765.

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

   Générer aussi `FACE_AGENT_TOKEN` et `AIOPS_CLIENT_SECRET` avec des valeurs
   distinctes. Générer `FACE_DATA_KEY` avec :

   ```powershell
   py -3.12 -m pip install -r face_agent\requirements.txt
   py -3.12 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

   Si le fichier déchiffré avec SOPS ne contient pas les nouvelles clés ci-dessous,
   les générer et les ajouter localement (ne pas exécuter ce bloc si elles existent
   déjà) :

   ```powershell
   $exerciseToken = py -3.12 -c "import secrets; print(secrets.token_hex(32))"
   $faceAgentToken = py -3.12 -c "import secrets; print(secrets.token_hex(32))"
   $aiopsSecret = py -3.12 -c "import secrets; print(secrets.token_hex(32))"
   $faceDataKey = py -3.12 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   if (-not (Select-String -Path .env -Pattern '^EXERCISE_TOKEN=' -Quiet)) {
     Add-Content -Path .env -Value "EXERCISE_TOKEN=$exerciseToken"
   }
   Add-Content -Path .env -Value @(
     "FACE_AGENT_TOKEN=$faceAgentToken",
     "AIOPS_CLIENT_SECRET=$aiopsSecret",
     "FACE_DATA_KEY=$faceDataKey"
   )
   Remove-Variable exerciseToken, faceAgentToken, aiopsSecret, faceDataKey
   ```

   Garder `.env` hors du dépôt et de toute archive. Pour utiliser SOPS, installer
   SOPS et Age sur le PC Hôte, garder la clé privée Age hors du workspace, puis
   déchiffrer localement le fichier chiffré vers `.env` :

   ```powershell
   sops --decrypt --input-type dotenv --output .env secrets\app.enc.env
   ```

   Vérifier que le `.env` contient des valeurs uniques pour `EXERCISE_TOKEN`,
   `REMEDIATION_TOKEN`, `FACE_AGENT_TOKEN` et `AIOPS_CLIENT_SECRET`.
   Ne jamais archiver une clé privée ni le `.env`.

3. Vérifier la configuration puis démarrer le cœur :

   ```powershell
   docker compose --env-file .env config --quiet
   docker compose --env-file .env up --build -d
   ```

4. Démarrer l'agent caméra sur le PC Hôte, dans un terminal PowerShell séparé :

   ```powershell
   py -3.12 -m pip install -r face_agent\requirements.txt
   py -3.12 -m face_agent.download_models
   py -m pip install platformio
   py -m platformio run -d firmware -e esp8266 -t upload --upload-port COM3
   py -3.12 -m face_agent.run
   ```

   Le service utilise la webcam USB du PC Hôte (index `CAMERA_INDEX`, défaut `0`).
   Il utilise aussi le port série de l'ESP8266 (`ESP_SERIAL_PORT`, défaut `COM3`) ;
   arrêter l'agent avant tout nouveau téléversement.
   Autoriser le port TCP 8765 dans le pare-feu Windows uniquement pour le réseau
   privé du laboratoire et Docker Desktop. Le service exige `FACE_AGENT_TOKEN` ;
   aucun flux vidéo ni échantillon facial n'est envoyé au navigateur.

5. Après le premier démarrage de Compose, importer les photos de référence de
   l'administrateur initial dans son profil facial chiffré :

   ```powershell
   py -3.12 -m face_agent.enroll operator --images photo
   ```

   Remplacer `operator` par `OPERATOR_USERNAME` si nécessaire. L'import valide les
   huit images, extrait localement leurs empreintes faciales et remplace le profil
   existant de cet utilisateur par ces empreintes chiffrées ; les photos ne sont pas
   conservées dans la base et la commande n'ouvre pas la webcam. Pour enrôler directement
   depuis la caméra, omettre `--images photo`. Ouvrir ensuite `http://localhost:8080`.
   L'identifiant doit d'abord être reconnu par la caméra, puis le mot de passe sera
   demandé. Les administrateurs gèrent les comptes et leurs profils faciaux dans la
   section **Habilitations faciales** du dashboard. Les profils sont chiffrés avec
   `FACE_DATA_KEY`.

   Pour tester la reconnaissance des huit références contre la webcam sans modifier
   le profil, lancer :

   ```powershell
   py -3.12 -m face_agent.test_live_match photo --led-on-mismatch
   ```

   La personne doit être devant la webcam pendant la capture. Toutes les images du
   dossier `photo` servent de références en mémoire et les captures live ne sont
   pas sauvegardées. Ce dossier n'est pas inclus dans l'archive de livraison.
   `--led-on-mismatch` envoie au port série ESP8266 (défaut `COM3`) le signal rouge
   si la majorité des captures échoue au seuil ou si aucun visage n'est détecté.
   La reconnaissance locale utilise SFace et YuNet, modèles OpenCV Zoo téléchargés
   par la commande ci-dessus puis vérifiés par SHA-256. `FACE_SIMILARITY_THRESHOLD`
   vaut 0.363 par défaut (similarité cosinus). Ce seuil est un réglage de prototype,
   pas une mesure de performance : teste les faux rejets et les fausses acceptations
   avec des personnes enrôlées et non enrôlées avant tout usage réel. Les modèles
   restent dans `face_agent\models` et ne sont pas versionnés.

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

Le script utilise uniquement le point d’accès du laboratoire : il demande une
vérification par la caméra USB du PC Hôte (l’opérateur doit être devant cette
caméra), authentifie l’opérateur, injecte une panne applicative contrôlée, émet huit paiements fictifs
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

- Documentation centralisée et point d’entrée unique : [`docs/README.md`](./docs/README.md)
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

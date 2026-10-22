# Authentification faciale et ESP8266

## Parcours de connexion

1. L'opérateur saisit son identifiant dans le dashboard.
2. L'authentification appelle le service `face_agent` exécuté sur le PC Hôte. Celui-ci
   ouvre la webcam USB locale, détecte un visage unique avec YuNet, calcule son
   empreinte SFace et la compare aux profils autorisés.
3. Si le visage est reconnu, la caméra est libérée, la LED verte clignote et le
   dashboard demande le mot de passe. Le défi facial expire après deux minutes et
   ne peut être consommé qu'une fois ; le clignotement s'arrête aussi à l'expiration
   ou si l'opérateur annule l'étape.
4. Le mot de passe correct délivre un jeton opérateur d'une heure. Un mot de passe
   incorrect déclenche dix impulsions rouges, efface le défi et ramène le formulaire
   à la saisie de l'identifiant.
5. Un visage inconnu laisse la LED rouge fixe 30 secondes. Un nouvel essai est alors
   possible. Deux échecs faciaux consécutifs verrouillent cet identifiant pendant
   cinq minutes ; le verrouillage est conservé dans SQLite.

Le compte initial est créé à partir de `OPERATOR_USERNAME` et `OPERATOR_PASSWORD`.
Après le premier démarrage, son profil facial doit être enrôlé depuis le PC Hôte :

```powershell
py -3.12 -m pip install -r face_agent\requirements.txt
py -3.12 -m face_agent.download_models
py -3.12 -m face_agent.run
py -3.12 -m face_agent.enroll operator --images photo
```

L'option `--images photo` valide puis importe les visages détectés dans chaque
image du dossier, calcule localement leurs empreintes SFace et enregistre ces
empreintes chiffrées dans le profil de l'utilisateur, sans conserver les photos ni
ouvrir la webcam. Cet import remplace son profil précédent. C'est ce profil que
l'API utilise pour la connexion ; une comparaison temporaire ne l'enrôle pas. Sans
cette option, l'enrôlement capture les visages depuis la caméra.

Pour un essai sans modifier la base des profils, comparer une photo locale à la
webcam :

```powershell
py -3.12 -m face_agent.test_live_match photo --led-on-mismatch
```

Le dossier contient la base de références temporaire : toutes ses images JPEG/PNG
compatibles sont converties en empreintes SFace en mémoire. La commande affiche
les fichiers chargés, le nombre de captures, les similarités cosinus et le résultat.
`--led-on-mismatch` est explicite : il envoie le motif rouge `face_denied` au
contrôleur série uniquement si le résultat est négatif. Les captures restent en
mémoire et ne sont pas enregistrées. Le test ne vérifie ni la vivacité ni l'identité
réelle et ne remplace pas un profil enrôlé avec plusieurs images.
Le dossier `photo` est exclu de l'archive de remise : les images biométriques restent
sur le PC Hôte.

Les administrateurs peuvent créer des comptes `admin` ou `operator`, enrôler de
nouveau leur visage ou supprimer leur compte et son profil depuis **Habilitations
faciales** dans le dashboard. Les mots de passe sont stockés avec PBKDF2-HMAC-SHA256.
Les profils sont enregistrés dans `face_agent\data\faces.sqlite3` et chiffrés avec
Fernet ; la clé `FACE_DATA_KEY` n'est jamais versionnée. Les échantillons ne sont
pas envoyés au navigateur ou aux conteneurs.
Conserver une copie de `FACE_DATA_KEY` dans le coffre de secrets de l'équipe :
sa perte rend les profils existants illisibles et impose un nouvel enrôlement.
L'enrôlement doit être supervisé, avec l'accord de la personne concernée.

## Déploiement de l'agent caméra

L'agent doit tourner sur le PC qui héberge la webcam USB. Il écoute sur le port
8765, et le conteneur `auth` le joint via `host.docker.internal`. Il faut autoriser
ce port dans le pare-feu Windows pour le réseau privé du laboratoire et Docker
Desktop seulement. L'agent exige `FACE_AGENT_TOKEN`, et la base biométrique locale
est protégée par `FACE_DATA_KEY`. Ne pas exposer ce port sur un réseau public.

`CAMERA_INDEX` sélectionne la caméra (défaut `0`).
`FACE_SIMILARITY_THRESHOLD` (défaut `0.363`) contrôle le seuil cosinus SFace. La
connexion exige une majorité de cinq captures live, plutôt qu'une seule image.
Les modèles YuNet (MIT) et SFace (Apache 2.0) proviennent d'OpenCV Zoo à une révision
fixée ; le téléchargement vérifie leur SHA-256 et les poids restent locaux.
Le seuil de référence n'est pas une mesure de performance : tester les faux rejets
et fausses acceptations avec des personnes enrôlées et non enrôlées dans les
conditions réelles.
Une caméra inaccessible
ou une erreur de reconnaissance bloque l'authentification interactive ; les
authentifications de service AIOps utilisent un secret de service dédié, sans
contourner le parcours humain.

## ESP8266

`firmware\` est le projet PlatformIO pour NodeMCU ESP8266. La carte communique
uniquement par USB série ; aucun réseau Wi-Fi ou broker MQTT n'est utilisé.
Brancher la carte au PC Hôte, vérifier le port dans le Gestionnaire de périphériques,
puis téléverser depuis le dépôt :

```powershell
py -m pip install platformio
py -m platformio run -d firmware -e esp8266 -t upload --upload-port COM3
```

Le relais série est intégré à `face_agent`, qui s'exécute sur le PC Hôte avec accès
au port USB. Il utilise `ESP_SERIAL_PORT` (défaut `COM3`) et `ESP_SERIAL_BAUD`
(défaut `115200`). Le service `auth` lui transmet les états par HTTP authentifié avec
`FACE_AGENT_TOKEN`. L'agent conserve le port série ouvert ; l'arrêter avant de
reprogrammer la carte ou d'ouvrir un moniteur série.

La LED verte est pilotée par D1 et la rouge par D2 ; le retour commun est relié à G
(GND). Utiliser une résistance série de 220 Ω sur chaque LED et confirmer le
câblage de la carte avant alimentation.

| État reçu | Signal LED |
|---|---|
| `off` | Éteinte |
| `password_pending` | Vert clignotant jusqu'au résultat du mot de passe |
| `granted` | Vert fixe pendant 30 secondes, puis éteinte |
| `face_denied` | Rouge fixe pendant 30 secondes, puis éteinte |
| `password_denied` | Dix impulsions rouges, puis éteinte |

## Limites du prototype

YuNet + SFace est une reconnaissance faciale locale de démonstration, pas un
dispositif biométrique certifié. Il n'y a pas de détection de vivacité et le seuil
par défaut n'est pas une mesure de performance. Évaluer les faux rejets et les
fausses acceptations avec consentement, documenter les conditions de test et ne pas
utiliser ce prototype seul pour protéger un système réel ou des données sensibles.

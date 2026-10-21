# Authentification faciale et ESP8266

## Parcours de connexion

1. L'opérateur saisit son identifiant dans le dashboard.
2. L'authentification appelle le service `face_agent` exécuté sur le PC Hôte. Celui-ci
   ouvre la webcam USB locale, détecte un visage unique et le compare aux profils
   autorisés avec OpenCV LBPH.
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
py -3.12 -m face_agent.run
py -3.12 -m face_agent.enroll operator
```

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

`CAMERA_INDEX` sélectionne la caméra (défaut `0`). `FACE_DISTANCE_THRESHOLD`
(défaut `55`) contrôle le seuil LBPH : sa calibration doit être faite avec la
caméra, la lumière et les personnes réellement utilisées. Une caméra inaccessible
ou une erreur de reconnaissance bloque l'authentification interactive ; les
authentifications de service AIOps utilisent un secret de service dédié, sans
contourner le parcours humain.

## ESP8266

`firmware\` est le projet PlatformIO pour NodeMCU ESP8266. Copier le fichier
d'exemple `include\secrets.example.h` en `include\secrets.h` et configurer le SSID
du point d'accès RESILIENCE-G<n>, son mot de passe, l'adresse Wi-Fi du PC Hôte, et
les identifiants MQTT de `.env`. Ne pas committer `secrets.h`.

Le broker Mosquitto n'est pas accessible anonymement et le port 1883 est lié par
défaut à `127.0.0.1`. Pour l'ESP8266, lier `MQTT_BIND_ADDRESS` à l'adresse du point
d'accès du PC Hôte. La LED bicolore commune-cathode est pilotée par D5 (rouge) et
D6 (vert), avec une résistance série de 220 Ω sur chaque anode ; confirmer le
câblage de la carte avant alimentation.

| État reçu | Signal LED |
|---|---|
| `off` | Éteinte |
| `password_pending` | Vert clignotant jusqu'au résultat du mot de passe |
| `granted` | Vert fixe pendant 30 secondes, puis éteinte |
| `face_denied` | Rouge fixe pendant 30 secondes, puis éteinte |
| `password_denied` | Dix impulsions rouges, puis éteinte |

## Limites du prototype

OpenCV Haar + LBPH est une reconnaissance faciale légère de démonstration, pas un
dispositif biométrique certifié. Il n'y a pas de détection de vivacité et le seuil
par défaut n'est pas une mesure de performance. Évaluer les faux rejets et les
fausses acceptations avec consentement, documenter les conditions de test et ne pas
utiliser ce prototype seul pour protéger un système réel ou des données sensibles.

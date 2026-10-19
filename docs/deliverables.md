# Rendus demandés par le sujet

Le sujet demande un dossier d’ingénierie PDF, une présentation PPTX, un Clip Chrono
MP4 de 60 secondes maximum, une archive des sources sans secrets et un démonstrateur
exécuté sur deux machines.

| Rendu | État ici | À compléter par le consortium |
|---|---|---|
| Dossier d’ingénierie et gouvernance PDF (8–12 pages indicatives) | Contenu technique préparé dans `docs/` et `rag/procedure_crise.md` | Mise en page PDF, résultats réels, matrice EBIOS validée, mesures de reprise, contributions nominatives |
| Support de présentation PPTX | Plan de présentation non généré | Ajouter nom/numéro du groupe, intervenants, arbitrages et captures réelles |
| Clip Chrono MP4 (≤60 s, sans coupe) | Scénario et critères disponibles dans `docs/incident-response.md` | Enregistrer la séquence live depuis les machines autorisées ; une vidéo ne peut pas être fabriquée à partir de tests non exécutés |
| Archive Code.zip | Générateur filtrant fourni (`scripts/package_release.py`) | Exécuter avec le numéro de groupe et inspecter le contenu avant remise |
| Démonstrateur local | Code préparé, mais non déployé dans cet environnement | Démarrer Docker Desktop, configurer le `.env`, essayer le PC Attaquant et collecter les preuves |

Le numéro d’équipe et l’identité/contribution de ses membres ne figurent pas dans le
workspace ; aucun nom ni preuve de soutenance ne doit être inventé. Le PDF d’origine
est le cahier des charges, pas le dossier de l’équipe.

Le workspace contenait également un fichier nommé `secrets/key.txt`. Son contenu
n’a pas été consulté et l’archive générée l’exclut ; avant toute remise, vérifier
localement qu’il ne s’agit pas d’une clé privée encore conservée dans le workspace.

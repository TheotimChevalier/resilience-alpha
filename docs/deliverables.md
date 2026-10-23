# Rendus demandés par le sujet

Le sujet demande un dossier d’ingénierie PDF, une présentation PPTX, un Clip Chrono
MP4 de 60 secondes maximum, une archive des sources sans secrets et un démonstrateur
exécuté sur deux machines.

| Rendu | État ici | À compléter par le consortium |
|---|---|---|
| Dossier d’ingénierie et gouvernance PDF (8–12 pages indicatives) | `resilience-alpha-documentation.pdf` : dossier structuré de 12 pages avec architecture ; source `docs/project-dossier.md` | Ajouter résultats réels complémentaires, matrice EBIOS validée, mesures répétées de reprise et contributions nominatives |
| Support de présentation PPTX | Plan de présentation non généré | Ajouter nom/numéro du groupe, intervenants, arbitrages et captures réelles |
| Clip Chrono MP4 (≤60 s, sans coupe) | Scénario et critères disponibles dans `docs/incident-response.md` | Enregistrer la séquence live depuis les machines autorisées ; une vidéo ne peut pas être fabriquée à partir de tests non exécutés |
| Archive Code.zip | Générateur filtrant fourni (`scripts/package_release.py`), incluant l'agent facial et le firmware ; `.env`, les clés, `secrets.h` et les bases biométriques sont exclus | Exécuter avec le numéro de groupe et inspecter le contenu avant remise |
| Démonstrateur local | Stack exécutée ; scénario contrôlé répété sur localhost avec paiement avant incident, huit 503, décision ML/AIOps et transactions après reprise | Répéter depuis un PC Attaquant distinct via le point d’accès de laboratoire ; conserver la capture continue et les journaux |

Le numéro d’équipe et l’identité/contribution de ses membres ne figurent pas dans le
workspace ; aucun nom ni preuve de soutenance ne doit être inventé. Le PDF d’origine
est le cahier des charges, pas le dossier de l’équipe. La matrice détaillée
exigence/preuve/travail restant est dans [`requirements-traceability.md`](./requirements-traceability.md).

Les derniers essais effectués depuis ce workspace prouvent le scénario local,
mais ne remplacent ni l’attaque depuis le second PC imposée par le sujet ni un Clip
Chrono filmé en continu. La configuration SOPS chiffrée ne doit pas être remplacée
par une clé privée dans l’archive des sources.

La copie locale `secrets/key.txt` n'est plus suivie par Git et l’archive générée
l’exclut ; son contenu n’a pas été consulté et le fichier local a été conservé.
Déplacer toute clé privée hors du workspace. Si cette clé a déjà été publiée, la
révoquer et la remplacer ; retirer le fichier du dernier commit ne purge pas l'historique.

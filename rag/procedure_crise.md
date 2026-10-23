# Procédure de gestion d'incident - Resilience Alpha

## 1. Description du Service
Le démonstrateur traite des transactions fictives via `POST /api/v1/pay`. Le frontal React
est publié sur le port 8080 et le WAF OWASP ModSecurity CRS sur le port 80. L'API n'est
pas publiée directement sur l'hôte.

## 2. Détection d'Incident
- Prometheus collecte les compteurs de paiements et la durée des transactions.
- AIOps forme un Isolation Forest sur des observations synthétiques nominales et analyse
  le débit, le ratio de réponses HTTP 5xx et la latence moyenne.
- Une prédiction d'anomalie n'engage la réponse que si le volume et le ratio d'échecs
  apportent aussi suffisamment d'éléments. Une erreur de collecte n'est pas assimilée à
  un incident et ne déclenche pas de remédiation.

## 3. Procédure de Rétablissement (Zero-Touch Recovery)
- L'injection contrôlée se fait par `POST /admin/inject-fault` avec le jeton de test
  `X-Remediation-Token`. Cette route ne sert qu'à l'exercice autorisé.
- AIOps exécute `POST /admin/remediate` avec son jeton dédié. Le défaut contrôlé est
  retiré sans redémarrer ni donner au détecteur l'accès au socket Docker.
- AIOps confirme `/health`, demande ensuite une transaction synthétique de 0,01 EUR
  par l'API authentifiée, et publie le résultat de reprise. Le succès métier, pas un
  redémarrage de conteneur, est la preuve de reprise.
- Le tableau de bord authentifié montre l'état, les événements d'incident, l'action
  de remédiation et le contrôle métier. Les journaux sont également envoyés à Loki.
- Une expiration de sécurité de trois minutes remet le démonstrateur en état nominal
  si l'orchestrateur ne termine pas l'exercice.

Les jetons et identifiants sont propres au laboratoire. Ne jamais les committer, les
afficher dans une capture ou les réutiliser hors des machines autorisées.
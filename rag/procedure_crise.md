# PROCÉDURE DE GESTION D'INCIDENT - PLATEFORME DE PAIEMENT RESILIENCE-ALPHA

## 1. Description du Service
La plateforme de paiement critique traite les transactions financières entrantes via l'endpoint `/api/v1/pay`.
Le trafic entrant transite par un WAF (OWASP ModSecurity CRS) sur le port 80 avant d'atteindre l'API sur le port 8000.

## 2. Détection d'Incident
- Les métriques sont collectées en continu par Prometheus (port 9090).
- Le moteur AIOps utilise un modèle non-supervisé Isolation Forest pour repérer les hausses de codes HTTP 503.
- En cas d'anomalie confirmée, le moteur déclenche une remédiation autonome sans intervention humaine.

## 3. Procédure de Rétablissement (Zero-Touch Recovery)
- Le point d'injection d'incident se trouve sur `/admin/inject-fault`.
- L'action de remédiation s'exécute automatiquement via `/admin/remediate`.
- Vérification post-incident obligatoire : validation d'une transaction nominale de test sur `/api/v1/pay`.
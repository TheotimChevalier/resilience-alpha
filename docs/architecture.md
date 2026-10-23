# Architecture et interfaces

## Composants

| Composant | Rôle | Accès réseau |
|---|---|---|
| Dashboard React/Tailwind + Nginx | Paiements de démonstration, santé, événements, assistant | Hôte `:8080` |
| WAF OWASP CRS | Filtre HTTP vers l’API | Hôte `:80` |
| Auth | Émet des jetons opérateur courts | Réseau Compose uniquement |
| Payment API / FastAPI | Contrôle les accès, persiste les transactions, expose santé et métriques | Réseau Compose uniquement |
| PostgreSQL | Stocke les transactions fictives | Réseau Compose uniquement |
| Prometheus | Scrape `/metrics` et fournit les observations AIOps | Hôte `127.0.0.1:9090` |
| Grafana | Dashboard provisionné Prometheus/Loki | Hôte `127.0.0.1:3000` |
| Loki | Reçoit les événements applicatifs | Réseau Compose uniquement |
| AIOps | Isolation Forest, déclenchement et vérification de la remédiation | Réseau Compose uniquement |
| Ollama + LangChain + Chroma RAG | Assistant documentaire local ; modèle `llama3.2:3b` (3B paramètres) | Profil Compose `ai`, réseau interne |

Le diagramme de flux est :

```text
PC navigateur / PC Attaquant
        |             |
   :8080 dashboard   :80 WAF
        |             |
        +------ auth / payment-api ------ PostgreSQL
                         |       |
                    Prometheus  Loki
                         |
                      AIOps ---- auth + payment-api (remédiation par jeton)
```

La base, les interfaces de gestion, les métriques, Loki, l’authentification et l’API
ne sont pas publiés sur l’hôte. Les deux ports publiés doivent être liés uniquement
à l’interface du réseau de démonstration. Les valeurs par défaut de Compose lient
ces ports à `127.0.0.1`; pour un PC Attaquant distinct, l’opérateur règle les deux
adresses de liaison sur l’interface Wi-Fi du laboratoire et contrôle le résultat avec
`docker compose ps`.

## Parcours d’un paiement normal

1. L’opérateur s’authentifie auprès du service `auth`. Un jeton HMAC limité à une
   heure est conservé en `sessionStorage` dans le navigateur.
2. Le dashboard envoie le paiement au WAF. L’API valide le jeton, les entrées et le
   montant avant d’écrire une transaction `VALIDATED` dans PostgreSQL.
3. L’API expose le résultat, mesure le statut HTTP et la durée, publie un événement
   à Loki et expose les métriques à Prometheus.
4. Le dashboard interroge la santé et, avec une session opérateur, l’état métier
   consolidé depuis l’API.

## Détection et reprise

Le PC Attaquant autorisé obtient un jeton d'exercice distinct et injecte une panne
contrôlée. Ce jeton n'autorise que cette injection ; le jeton `REMEDIATION_TOKEN`
est réservé à AIOps. Le PC Attaquant envoie ensuite des paiements fictifs. L’API répond
503 pendant l’exercice et n’écrit aucune transaction échouée en base. Prometheus
observe le débit, la durée et la proportion de 5xx. AIOps construit le vecteur de
caractéristiques, le présente à un Isolation Forest entraîné sur des observations nominales synthétiques (comptage
Poisson du volume normal), puis exige un minimum d’évidence métier avant d’agir.

AIOps publie la décision et ses métriques dans le journal métier, appelle l’endpoint
interne authentifié de remédiation, obtient un jeton
opérateur et vérifie la santé ainsi qu’une nouvelle transaction de 0,01 EUR. Il
enregistre le résultat. Le dashboard, les logs Loki et Grafana donnent les preuves
avant, pendant et après la reprise. Le détecteur n’a pas accès au socket Docker ni
au mot de passe PostgreSQL.

## Limites de périmètre

- La panne est un point d’injection de laboratoire au niveau applicatif, pas une
  exploitation arbitraire d’un service tiers ni une preuve de résistance générale.
- Les métriques AIOps sont analysées sur une fenêtre Prometheus de 60 secondes ;
  la latence initiale de détection dépend donc du scrapping et du trafic observé.
- Le modèle est entraîné sur des données nominales synthétiques à l’initialisation ;
  la qualité des seuils dépend d’essais documentés sur la machine de démonstration.
- Les distributions, le jeu d'évaluation et les limites des métriques ML sont décrits
  dans [`ml-experiment.md`](./ml-experiment.md).
- L’assistant RAG est séparé de la remédiation, authentifié par jeton opérateur et
  ne possède aucune route d’administration. Son index est synchronisé au démarrage
  avec les documents Markdown montés en lecture seule ; les réponses exposent les
  chemins de leurs sources.
- Cette architecture de workshop n’est pas une architecture bancaire certifiée.

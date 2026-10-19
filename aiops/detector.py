import time
import requests
import docker
import numpy as np
from sklearn.ensemble import IsolationForest

PROMETHEUS_URL = "http://prometheus:9090/api/v1/query"
# On observe la latence moyenne : si elle explose ou timeout, c'est un DoS.
METRIC_QUERY = 'sum(rate(http_request_duration_seconds_sum[1m])) / sum(rate(http_request_duration_seconds_count[1m])) or vector(0)'

def get_latency():
    try:
        r = requests.get(PROMETHEUS_URL, params={'query': METRIC_QUERY}, timeout=3)
        res = r.json()['data']['result']
        return float(res[0]['value'][1]) if res else 0.0
    except Exception:
        # Si Prometheus n'arrive plus à joindre l'API (Timeout/DoS), on force une valeur aberrante
        return 99.0 

def remediate_infrastructure():
    print("[AIOps-Engine] Initialisation de la reprise au niveau infrastructure...")
    try:
        client = docker.from_env()
        # On cible physiquement le conteneur en panne
        container = client.containers.get('resilience-payment-api')
        print("[AIOps-Engine] Envoi du signal SIGTERM (Restarting container)...")
        container.restart(timeout=5)
        print("[✓ SUCCÈS] Conteneur redémarré. Zero-Touch Recovery terminé.")
        return True
    except Exception as e:
        print(f"[X ÉCHEC] Erreur Docker : {e}")
        return False

def main():
    print("[AIOps] Modèle ML : Entraînement sur la latence nominale (0.05s - 0.15s)...")
    baseline = np.random.normal(loc=0.10, scale=0.02, size=(100, 1))
    model = IsolationForest(contamination=0.05, random_state=42)
    model.fit(baseline)
    print("[AIOps] Surveillance active.")

    incident_mode = False

    while True:
        latency = get_latency()
        
        # Ignorer le silence réseau : s'il n'y a pas de requêtes, il n'y a pas d'incident.
        if latency == 0.0:
            if incident_mode:
                print("[AIOps] Statut de l'infrastructure : NOMINAL (Trafic à vide).")
                incident_mode = False
            time.sleep(3)
            continue

        prediction = model.predict(np.array([[latency]]))[0]

        # On ne déclenche l'alarme que si c'est une VRAIE latence excessive (> 2 secondes) ou un crash
        if prediction == -1 and latency > 2.0 and not incident_mode:
            incident_mode = True
            print(f"\n[ALERTE CRITIQUE] Anomalie détectée ! Latence aberrante : {latency:.2f}s")
            print(">> L'API ne répond plus (Saturation potentielle).")
            remediate_infrastructure()
            # On laisse le temps au conteneur de rebooter avant de reprendre la surveillance
            time.sleep(15) 
            
        elif prediction == 1 and incident_mode:
            print("[AIOps] Statut de l'infrastructure : NOMINAL.")
            incident_mode = False

        time.sleep(3)

if __name__ == "__main__":
    main()
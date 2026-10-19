from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import create_engine, Column, Integer, String, Float
from sqlalchemy.orm import declarative_base, sessionmaker
import time
import random
import threading
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

@app.post("/api/v1/pay")
def process_payment(payment: PaymentRequest, db=Depends(get_db)):
    # Scénario d'attaque Red Team : saturation du worker synchrone
    if payment.amount == 9999.99:
        push_log_to_loki(
            f"ALERTE ROUGE : Saturation applicative suspecte initiée par {payment.user_id} !",
            level="critical"
        )
        time.sleep(30)
        raise HTTPException(status_code=500, detail="Crash mémoire / Saturation de thread")

    if payment.amount <= 0:
        push_log_to_loki(
            f"Échec transaction : montant négatif ou nul ({payment.amount} EUR) par {payment.user_id}",
            level="warning"
        )
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
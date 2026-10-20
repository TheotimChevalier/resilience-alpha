import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import random
import threading
import time
from collections import deque

import requests
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import Counter, Gauge, Histogram
from pydantic import BaseModel, Field
from prometheus_fastapi_instrumentator import Instrumentator
from sqlalchemy import Column, Float, Integer, String, create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("payment-api")

DATABASE_URL = os.getenv("DATABASE_URL")
TOKEN_SECRET = os.getenv("AUTH_SIGNING_SECRET")
REMEDIATION_TOKEN = os.getenv("REMEDIATION_TOKEN")
EXERCISE_TOKEN = os.getenv("EXERCISE_TOKEN")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be set")
if not TOKEN_SECRET or len(TOKEN_SECRET) < 32:
    raise RuntimeError("AUTH_SIGNING_SECRET must contain at least 32 characters")
if not REMEDIATION_TOKEN or len(REMEDIATION_TOKEN) < 24:
    raise RuntimeError("REMEDIATION_TOKEN must contain at least 24 characters")
if not EXERCISE_TOKEN or len(EXERCISE_TOKEN) < 24:
    raise RuntimeError("EXERCISE_TOKEN must contain at least 24 characters")

Base = declarative_base()


class TransactionDB(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, nullable=False)


engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    engine_options["connect_args"] = {"check_same_thread": False}
    if DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
        engine_options["poolclass"] = StaticPool
engine = create_engine(DATABASE_URL, **engine_options)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base.metadata.create_all(bind=engine)

PAYMENT_REQUESTS = Counter(
    "resilience_payment_requests_total",
    "Payment requests completed, grouped by HTTP status.",
    ["status"],
)
PAYMENT_DURATION = Histogram(
    "resilience_payment_duration_seconds",
    "Payment request processing duration.",
)
INCIDENT_ACTIVE = Gauge(
    "resilience_incident_active",
    "Whether a controlled payment incident is currently active.",
)
MODEL_ANOMALY = Gauge(
    "resilience_model_anomaly",
    "Whether the most recent actionable detector decision was anomalous.",
)
MODEL_ANOMALY_SCORE = Gauge(
    "resilience_model_anomaly_score",
    "Decision function score for the most recent actionable anomaly.",
)
RECOVERY_VERIFIED = Gauge(
    "resilience_recovery_verified",
    "Whether the latest recovery was verified by a business transaction.",
)
INCIDENT_EVENTS = Counter(
    "resilience_incident_events_total",
    "Business incident and recovery events recorded by the API.",
    ["event_type"],
)
INCIDENTS = deque(maxlen=100)
authorization_denial_state: dict[str, tuple[float, int]] = {}
state_lock = threading.Lock()
injected_fault_until = 0.0
active_incident_id = None

app = FastAPI(title="Resilience Alpha Payment API", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:8080").split(","),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-Exercise-Token",
        "X-Remediation-Token",
    ],
)


class PaymentRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=80)
    amount: float = Field(gt=0, le=100000)
    destination_account: str = Field(min_length=1, max_length=80)


class RecoveryResult(BaseModel):
    recovered: bool
    check_transaction_id: str | None = Field(default=None, max_length=80)
    message: str = Field(min_length=1, max_length=500)


class DetectionResult(BaseModel):
    model_anomaly: bool
    actionable: bool
    anomaly_score: float
    request_count: float = Field(ge=0)
    error_ratio: float = Field(ge=0, le=1)
    mean_latency: float = Field(ge=0)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _record_event(kind: str, message: str, **details):
    event = {
        "timestamp": time.time(),
        "type": kind,
        "message": message,
        "actor": details.pop("actor", "system"),
        **details,
    }
    with state_lock:
        INCIDENTS.appendleft(event)
    INCIDENT_EVENTS.labels(event_type=kind).inc()
    if kind == "incident":
        INCIDENT_ACTIVE.set(1)
        RECOVERY_VERIFIED.set(0)
    elif kind == "detection":
        MODEL_ANOMALY.set(1 if event.get("model_anomaly") else 0)
        MODEL_ANOMALY_SCORE.set(float(event.get("anomaly_score", 0)))
    elif kind == "recovery":
        RECOVERY_VERIFIED.set(1 if event.get("status") == "recovered" else 0)
    elif kind == "recovery_failed":
        RECOVERY_VERIFIED.set(0)
    audit_record = json.dumps(event, separators=(",", ":"), default=str)
    push_log_to_loki(audit_record, "critical" if kind == "incident" else "info")
    logger.info("%s", audit_record)


def _record_authorization_denial(capability: str) -> None:
    now = time.monotonic()
    with state_lock:
        last_recorded, suppressed = authorization_denial_state.get(
            capability,
            (float("-inf"), 0),
        )
        if now - last_recorded < 60:
            authorization_denial_state[capability] = (last_recorded, suppressed + 1)
            return
        authorization_denial_state[capability] = (now, 0)
    _record_event(
        "authorization_denied",
        "Request rejected: credential was invalid or missing.",
        capability=capability,
        suppressed_attempts=suppressed,
        actor="unknown",
    )


def push_log_to_loki(message: str, level: str = "info"):
    payload = {
        "streams": [
            {
                "stream": {"app": "payment-api", "level": level},
                "values": [[str(int(time.time() * 1e9)), message]],
            }
        ]
    }

    def send():
        try:
            response = requests.post(
                "http://loki:3100/loki/api/v1/push",
                json=payload,
                timeout=2,
            )
            response.raise_for_status()
        except requests.RequestException:
            logger.exception("Could not deliver an application log to Loki")

    threading.Thread(target=send, daemon=True).start()


def _decode_payload(encoded: str) -> dict:
    return json.loads(base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)))


def require_operator(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Operator bearer token required")
    token = authorization.removeprefix("Bearer ")
    try:
        header, payload, signature = token.split(".")
        signed = f"{header}.{payload}".encode("ascii")
        expected = _b64url(hmac.new(TOKEN_SECRET.encode(), signed, hashlib.sha256).digest())
        claims = _decode_payload(payload)
        if not hmac.compare_digest(signature, expected):
            raise ValueError("signature mismatch")
        if claims.get("iss") != "resilience-auth" or float(claims.get("exp", 0)) <= time.time():
            raise ValueError("expired or invalid issuer")
        return str(claims["sub"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError, binascii.Error, UnicodeDecodeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired operator token") from exc


def require_remediator(
    token: str | None = Header(default=None, alias="X-Remediation-Token"),
) -> str:
    if not token or not hmac.compare_digest(token, REMEDIATION_TOKEN):
        _record_authorization_denial("remediation")
        raise HTTPException(status_code=403, detail="Remediation credential required")
    return "aiops-detector"


def require_exercise(
    token: str | None = Header(default=None, alias="X-Exercise-Token"),
) -> str:
    if not token or not hmac.compare_digest(token, EXERCISE_TOKEN):
        _record_authorization_denial("exercise")
        raise HTTPException(status_code=403, detail="Exercise credential required")
    return "redteam-exercise"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health")
def health_check():
    global injected_fault_until
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        logger.exception("Database health check failed")
        raise HTTPException(status_code=503, detail="Payment database unavailable") from exc
    expired_incident_id = None
    with state_lock:
        if injected_fault_until and injected_fault_until <= time.time():
            expired_incident_id = active_incident_id
            injected_fault_until = 0
        fault_active = injected_fault_until > time.time()
    if expired_incident_id:
        INCIDENT_ACTIVE.set(0)
        _record_event(
            "recovery_failed",
            "Incident safety timeout expired; service returned to normal.",
            incident_id=expired_incident_id,
            status="safety_timeout",
        )
    return {"status": "degraded" if fault_active else "ok", "incident_active": fault_active}


@app.post("/api/v1/pay")
def process_payment(
    payment: PaymentRequest,
    user_id: str = Depends(require_operator),
    db=Depends(get_db),
):
    started = time.perf_counter()
    status = "500"
    expired_incident = False
    try:
        global injected_fault_until
        with state_lock:
            if injected_fault_until and injected_fault_until <= time.time():
                injected_fault_until = 0
                expired_incident = True
                INCIDENT_ACTIVE.set(0)
            if injected_fault_until > time.time():
                raise HTTPException(status_code=503, detail="Controlled resilience incident is active")
        if expired_incident:
            _record_event(
                "recovery_failed",
                "Incident safety timeout expired; service returned to normal without AIOps verification.",
                incident_id=active_incident_id,
                status="safety_timeout",
            )

        time.sleep(random.uniform(0.05, 0.15))
        transaction = TransactionDB(
            user_id=payment.user_id,
            amount=payment.amount,
            status="VALIDATED",
        )
        db.add(transaction)
        db.commit()
        db.refresh(transaction)
        transaction_id = f"TXN-{transaction.id}-{random.randint(100, 999)}"
        _record_event(
            "payment",
            f"{transaction_id} validated for {payment.user_id}: {payment.amount:.2f} EUR.",
            transaction_id=transaction_id,
            amount=payment.amount,
            actor=user_id,
        )
        status = "200"
        return {
            "status": "success",
            "transaction_id": transaction_id,
            "message": "Simulated payment recorded successfully",
        }
    except HTTPException as exc:
        status = str(exc.status_code)
        if exc.status_code == 503:
            _record_event(
                "payment_failed",
                "Payment rejected while the injected incident is active.",
                actor=user_id,
            )
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        status = "503"
        logger.exception("Payment persistence failed")
        raise HTTPException(status_code=503, detail="Payment database unavailable") from exc
    finally:
        PAYMENT_REQUESTS.labels(status=status).inc()
        PAYMENT_DURATION.observe(time.perf_counter() - started)


@app.post("/admin/inject-fault", status_code=202)
def inject_fault(actor: str = Depends(require_exercise)):
    global injected_fault_until, active_incident_id
    with state_lock:
        if injected_fault_until > time.time():
            incident_id = active_incident_id
            already_active = True
        else:
            active_incident_id = f"INC-{int(time.time())}"
            injected_fault_until = time.time() + 180
            INCIDENT_ACTIVE.set(1)
            RECOVERY_VERIFIED.set(0)
            incident_id = active_incident_id
            already_active = False
    if already_active:
        _record_event(
            "exercise_rejected",
            "Fault injection rejected because a controlled incident is already active.",
            incident_id=incident_id,
            status="already_active",
            actor=actor,
        )
        raise HTTPException(status_code=409, detail="An incident is already active")
    _record_event(
        "incident",
        "Controlled payment-service interruption injected by the authorized Red Team exercise.",
        incident_id=incident_id,
        status="detected",
        actor=actor,
    )
    return {"incident_id": incident_id, "status": "injected", "safety_timeout_seconds": 180}


@app.post("/admin/remediate")
def remediate(actor: str = Depends(require_remediator)):
    global injected_fault_until
    with state_lock:
        if not injected_fault_until:
            already_nominal = True
            incident_id = active_incident_id
        else:
            already_nominal = False
            injected_fault_until = 0
            INCIDENT_ACTIVE.set(0)
            incident_id = active_incident_id
    if already_nominal:
        _record_event(
            "remediation",
            "No controlled fault was active; no corrective action was needed.",
            incident_id=incident_id,
            status="already_nominal",
            actor=actor,
        )
        return {"status": "already_nominal"}
    _record_event(
        "remediation",
        "AIOps remediation cleared the controlled fault without restarting the database.",
        incident_id=incident_id,
        status="verifying",
        actor=actor,
    )
    return {"incident_id": incident_id, "status": "remediated"}


@app.post("/ops/detection", status_code=202)
def record_detection(
    result: DetectionResult,
    actor: str = Depends(require_remediator),
):
    with state_lock:
        incident_id = active_incident_id
    _record_event(
        "detection",
        "Isolation Forest classified the observed payment signals as anomalous.",
        incident_id=incident_id,
        model_anomaly=result.model_anomaly,
        actionable=result.actionable,
        anomaly_score=result.anomaly_score,
        request_count=result.request_count,
        error_ratio=result.error_ratio,
        mean_latency=result.mean_latency,
        actor=actor,
    )
    return {"status": "recorded"}


@app.post("/ops/recovery-result")
def recovery_result(
    result: RecoveryResult,
    actor: str = Depends(require_remediator),
):
    with state_lock:
        incident_id = active_incident_id
    _record_event(
        "recovery" if result.recovered else "recovery_failed",
        result.message,
        incident_id=incident_id,
        status="recovered" if result.recovered else "failed",
        check_transaction_id=result.check_transaction_id,
        actor=actor,
    )
    return {"incident_id": incident_id, "status": "recovered" if result.recovered else "failed"}


@app.get("/ops/state")
def operations_state(user_id: str = Depends(require_operator)):
    with engine.connect() as connection:
        totals = connection.execute(
            text("SELECT COUNT(*) AS transactions, COALESCE(SUM(amount), 0) AS volume FROM transactions")
        ).mappings().one()
    with state_lock:
        recent_events = list(INCIDENTS)
        fault_active = injected_fault_until > time.time()
        incident_id = active_incident_id
    current_incident_events = [
        event for event in recent_events if event.get("incident_id") == incident_id
    ]
    latest_detection = next(
        (event for event in current_incident_events if event["type"] == "detection"),
        None,
    )
    if fault_active:
        incident_phase = "incident_active"
    elif any(
        event["type"] == "recovery_failed" for event in current_incident_events
    ):
        incident_phase = "recovery_failed"
    elif any(
        event["type"] == "recovery" and event.get("status") == "recovered"
        for event in current_incident_events
    ):
        incident_phase = "recovered"
    elif any(
        event["type"] == "remediation" and event.get("status") == "verifying"
        for event in current_incident_events
    ):
        incident_phase = "verifying"
    elif latest_detection:
        incident_phase = "detected"
    else:
        incident_phase = "nominal"
    return {
        "api": "degraded" if fault_active else "operational",
        "incident_active": fault_active,
        "incident_id": incident_id,
        "incident_phase": incident_phase,
        "latest_detection": latest_detection,
        "events": recent_events,
        "transactions": totals["transactions"],
        "volume": float(totals["volume"]),
    }


Instrumentator().instrument(app).expose(app, include_in_schema=False)

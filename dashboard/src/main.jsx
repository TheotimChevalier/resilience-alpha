import React, { useCallback, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";

const apiBase = import.meta.env.VITE_API_BASE_URL || "";

function readSessionClaims() {
  const token = sessionStorage.getItem("operatorToken");
  if (!token) return {};
  try {
    const payload = token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
    return JSON.parse(atob(payload.padEnd(Math.ceil(payload.length / 4) * 4, "=")));
  } catch {
    return {};
  }
}

function Icon({ name, size = 18 }) {
  const paths = {
    activity: <><path d="M3 12h4l3-8 4 16 3-8h4" /></>,
    arrow: <><path d="M7 17 17 7M7 7h10v10" /></>,
    check: <><path d="m5 12 4 4L19 6" /></>,
    chevron: <><path d="m9 18 6-6-6-6" /></>,
    clock: <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>,
    credit: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 10h18" /></>,
    pulse: <><path d="M2 12h4l3-7 5 14 3-7h5" /></>,
    shield: <><path d="M12 22s8-4 8-11V5l-8-3-8 3v6c0 7 8 11 8 11Z" /><path d="m9 12 2 2 4-4" /></>,
    spark: <><path d="m12 3 1.9 5.8L20 11l-6.1 2.2L12 19l-1.9-5.8L4 11l6.1-2.2L12 3Z" /><path d="m19 14 1.3 2.7L23 18l-2.7 1.3L19 22l-1.3-2.7L15 18l2.7-1.3L19 14Z" /></>,
    terminal: <><rect x="3" y="4" width="18" height="16" rx="2" /><path d="m7 9 3 3-3 3m6 0h4" /></>,
    wallet: <><rect x="3" y="6" width="18" height="15" rx="2" /><path d="M3 9V6a2 2 0 0 1 2-2h13m-1 9h4" /><circle cx="17" cy="13" r=".5" /></>,
  };

  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {paths[name]}
    </svg>
  );
}

function App() {
  const [health, setHealth] = useState("checking");
  const [amount, setAmount] = useState("25.00");
  const [isPaying, setIsPaying] = useState(false);
  const [token, setToken] = useState(() => sessionStorage.getItem("operatorToken") || "");
  const [username, setUsername] = useState("");
  const [authenticatedUsername, setAuthenticatedUsername] = useState(() => readSessionClaims().sub || "");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [isLoggingIn, setIsLoggingIn] = useState(false);
  const [loginStep, setLoginStep] = useState("username");
  const [faceChallenge, setFaceChallenge] = useState("");
  const [retrySeconds, setRetrySeconds] = useState(0);
  const [role, setRole] = useState(() => readSessionClaims().role || "");
  const [adminUsers, setAdminUsers] = useState([]);
  const [newUser, setNewUser] = useState({ username: "", password: "", role: "operator" });
  const [adminError, setAdminError] = useState("");
  const [isManagingUsers, setIsManagingUsers] = useState(false);
  const [events, setEvents] = useState([]);
  const [transactions, setTransactions] = useState(0);
  const [volume, setVolume] = useState(0);
  const [incidentPhase, setIncidentPhase] = useState("nominal");
  const [latestDetection, setLatestDetection] = useState(null);

  const addEvent = useCallback((message, type = "info") => {
    setEvents((current) => [
      { id: `${Date.now()}-${Math.random()}`, time: new Date(), message, type },
      ...current,
    ].slice(0, 12));
  }, []);

  const checkHealth = useCallback(async () => {
    try {
      const response = await fetch(`${apiBase}/health`, { signal: AbortSignal.timeout(5000) });
      const result = await response.json();
      setHealth(result.status === "ok" ? "online" : "degraded");
    } catch {
      setHealth("offline");
    }
  }, []);

  useEffect(() => {
    checkHealth();
    const interval = window.setInterval(checkHealth, 5000);
    return () => window.clearInterval(interval);
  }, [checkHealth]);

  useEffect(() => {
    if (!token) return undefined;
    let active = true;
    const loadOperations = async () => {
      try {
        const response = await fetch(`${apiBase}/ops/state`, {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(5000),
        });
        if (response.status === 401) {
          sessionStorage.removeItem("operatorToken");
          if (active) {
            setToken("");
            setRole("");
            setAuthenticatedUsername("");
          }
          return;
        }
        if (!response.ok) throw new Error(`État opérationnel indisponible (${response.status})`);
        const result = await response.json();
        if (!active) return;
        setHealth(result.api === "operational" ? "online" : "degraded");
        setEvents(result.events.map((entry, index) => ({
          id: `${entry.timestamp}-${index}`,
          time: new Date(entry.timestamp * 1000),
          message: entry.message,
          type: entry.type === "recovery" || entry.type === "payment" ? "success" :
            entry.type === "incident" || entry.type === "payment_failed" || entry.type === "recovery_failed" ? "error" : "info",
        })));
        setTransactions(result.transactions);
        setVolume(result.volume);
        setIncidentPhase(result.incident_phase);
        setLatestDetection(result.latest_detection);
      } catch {
        if (active) addEvent("Journal opérationnel momentanément indisponible.", "error");
      }
    };
    loadOperations();
    const interval = window.setInterval(loadOperations, 3000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, [token, addEvent]);

  useEffect(() => {
    if (!retrySeconds) return undefined;
    const interval = window.setInterval(() => {
      setRetrySeconds((seconds) => Math.max(0, seconds - 1));
    }, 1000);
    return () => window.clearInterval(interval);
  }, [retrySeconds]);

  const loadAdminUsers = useCallback(async () => {
    if (!token || role !== "admin") return;
    const response = await fetch(`${apiBase}/auth/admin/users`, {
      headers: { Authorization: `Bearer ${token}` },
      signal: AbortSignal.timeout(65000),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Gestion des habilitations indisponible.");
    setAdminUsers(result.users);
  }, [token, role]);

  useEffect(() => {
    if (role !== "admin") return;
    loadAdminUsers().catch((error) => setAdminError(error.message));
  }, [role, loadAdminUsers]);

  async function verifyFace(event) {
    event.preventDefault();
    setIsLoggingIn(true);
    setLoginError("");
    try {
      const response = await fetch(`${apiBase}/auth/face/verify`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim() }),
        signal: AbortSignal.timeout(65000),
      });
      const result = await response.json();
      if (!response.ok) {
        const retry = Number(response.headers.get("Retry-After") || 0);
        if (response.status === 401 || response.status === 423) {
          setUsername("");
          setRetrySeconds(retry);
        }
        throw new Error(result.detail || "Identification faciale refusée.");
      }
      setUsername(username.trim());
      setFaceChallenge(result.challenge_id);
      setLoginStep("password");
      setRetrySeconds(0);
    } catch (error) {
      setLoginError(error.message || "Service de reconnaissance indisponible.");
    } finally {
      setIsLoggingIn(false);
    }
  }

  async function signIn(event) {
    event.preventDefault();
    setIsLoggingIn(true);
    setLoginError("");
    try {
      const response = await fetch(`${apiBase}/auth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password, challenge_id: faceChallenge }),
        signal: AbortSignal.timeout(5000),
      });
      const result = await response.json();
      if (!response.ok) {
        setPassword("");
        if (response.status === 401) setUsername("");
        setFaceChallenge("");
        setLoginStep("username");
        setRetrySeconds(response.status === 401 ? 10 : 0);
        throw new Error(result.detail || "Connexion refusée.");
      }
      sessionStorage.setItem("operatorToken", result.access_token);
      setToken(result.access_token);
      setRole(result.role);
      setAuthenticatedUsername(result.username);
      setPassword("");
    } catch (error) {
      setLoginError(error.message || "Service d’authentification indisponible.");
    } finally {
      setIsLoggingIn(false);
    }
  }

  function signOut() {
    sessionStorage.removeItem("operatorToken");
    setToken("");
    setRole("");
    setAuthenticatedUsername("");
    setUsername("");
    setLoginStep("username");
    setFaceChallenge("");
    setEvents([]);
  }

  async function createUser(event) {
    event.preventDefault();
    setIsManagingUsers(true);
    setAdminError("");
    try {
      const response = await fetch(`${apiBase}/auth/admin/users`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify(newUser),
        signal: AbortSignal.timeout(10000),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Création du compte refusée.");
      setNewUser({ username: "", password: "", role: "operator" });
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error.message);
    } finally {
      setIsManagingUsers(false);
    }
  }

  async function enrollFace(targetUsername) {
    setIsManagingUsers(true);
    setAdminError(`Enrôlement de ${targetUsername} en cours : regardez la caméra du PC hôte.`);
    try {
      const response = await fetch(`${apiBase}/auth/admin/users/${encodeURIComponent(targetUsername)}/face`, {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(65000),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Enrôlement facial refusé.");
      setAdminError(`Visage enregistré pour ${targetUsername} (${result.samples} images).`);
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error.message);
    } finally {
      setIsManagingUsers(false);
    }
  }

  async function deleteUser(targetUsername) {
    if (!window.confirm(`Supprimer le compte et le profil facial de ${targetUsername} ?`)) return;
    setIsManagingUsers(true);
    setAdminError("");
    try {
      const response = await fetch(`${apiBase}/auth/admin/users/${encodeURIComponent(targetUsername)}`, {
        method: "DELETE",
        headers: { Authorization: `Bearer ${token}` },
        signal: AbortSignal.timeout(10000),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Suppression refusée.");
      await loadAdminUsers();
    } catch (error) {
      setAdminError(error.message);
    } finally {
      setIsManagingUsers(false);
    }
  }

  async function cancelIdentification() {
    if (faceChallenge) {
      try {
        const response = await fetch(`${apiBase}/auth/face/cancel`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ challenge_id: faceChallenge }),
          signal: AbortSignal.timeout(5000),
        });
        if (!response.ok) throw new Error(`Annulation refusée (${response.status}).`);
      } catch {
        setLoginError("Annulation non confirmée par le service d’authentification.");
      }
    }
    setLoginStep("username");
    setFaceChallenge("");
    setPassword("");
  }

  async function sendPayment(event) {
    event.preventDefault();
    const parsedAmount = Number(amount);
    if (!Number.isFinite(parsedAmount) || parsedAmount <= 0) {
      addEvent("Montant invalide — saisissez un montant supérieur à 0 €.", "error");
      return;
    }

    setIsPaying(true);
    addEvent(`Paiement de ${parsedAmount.toFixed(2)} € initié…`);

    try {
      const response = await fetch(`${apiBase}/api/v1/pay`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          user_id: "CLIENT-WEB",
          amount: parsedAmount,
          destination_account: "ACC-RECV",
        }),
        signal: AbortSignal.timeout(35000),
      });
      const result = await response.json();
      if (!response.ok) {
        addEvent(`Paiement refusé (${response.status}) : ${result.detail || "erreur API"}`, "error");
        return;
      }

      setTransactions((count) => count + 1);
      setVolume((current) => current + parsedAmount);
      addEvent(`${result.transaction_id} — ${parsedAmount.toFixed(2)} € transférés avec succès.`, "success");
    } catch {
      addEvent("API injoignable ou délai de réponse dépassé. Vérifiez le service de paiement.", "error");
    } finally {
      setIsPaying(false);
      checkHealth();
    }
  }

  const statusLabels = {
    checking: "Vérification en cours",
    online: "Tous les systèmes opérationnels",
    degraded: "Incident détecté",
    offline: "API indisponible",
  };

  return (
    <div className="app-shell min-h-screen text-slate-100">
      <aside className="sidebar">
        <a className="brand" href="#" aria-label="Resilience Alpha, accueil">
          <span className="brand-mark"><Icon name="pulse" size={21} /></span>
          <span className="brand-name">resilience<span>alpha</span></span>
        </a>

        <div className="workspace-label">ESPACE DE TRAVAIL</div>
        <button className="workspace-switcher" type="button">
          <span className="workspace-avatar">RA</span>
          <span className="workspace-copy"><strong>Démo locale</strong><small>Environnement de test</small></span>
          <span className="switcher-dot" />
        </button>

        <div className="nav-label">PLATEFORME</div>
        <nav className="navigation" aria-label="Navigation principale">
          <a className="nav-item active" href="#overview"><Icon name="activity" />Vue d’ensemble<span className="nav-active-dot" /></a>
          <a className="nav-item" href="#payments"><Icon name="wallet" />Paiements</a>
          <a className="nav-item" href="#events"><Icon name="terminal" />Journal d’événements</a>
        </nav>

        <div className="sidebar-bottom">
          <div className="sidebar-status">
            <span className={`status-indicator ${health}`} />
            <div><strong>{health === "online" ? "API opérationnelle" : health === "checking" ? "Vérification…" : health === "degraded" ? "Incident détecté" : "API déconnectée"}</strong><small>Dernière vérification automatique</small></div>
          </div>
          <div className="sidebar-footer"><span className="footer-avatar">{token ? authenticatedUsername.slice(0, 2).toUpperCase() : "?"}</span><span><strong>{token ? authenticatedUsername : "Non connecté"}</strong><small>{token ? role === "admin" ? "Administrateur" : "Opérateur" : "Authentification requise"}</small></span><span className="footer-more">•••</span></div>
        </div>
      </aside>

      <main className="main-panel" id="overview">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><Icon name="chevron" size={14} /><strong>Vue d’ensemble</strong></div>
          <div className="topbar-right">
            <span className="environment-chip"><span />LABORATOIRE</span>
            <span className="topbar-divider" />
            <span className="current-date">{new Intl.DateTimeFormat("fr-FR", { dateStyle: "full" }).format(new Date())}</span>
            {token && <button className="signout-button" type="button" onClick={signOut}>Se déconnecter</button>}
            <button className="avatar-button" type="button" aria-label="Profil utilisateur">{token ? authenticatedUsername.slice(0, 2).toUpperCase() : "?"}</button>
          </div>
        </header>

        <div className="page-content">
          <section className="page-heading">
            <div>
              <div className="eyebrow"><span className="eyebrow-line" />CENTRE DE CONTRÔLE</div>
              <h1>Vue d’ensemble<span>.</span></h1>
              <p>Supervisez vos opérations et gardez le contrôle de vos paiements.</p>
            </div>
            <div className={`health-pill ${health}`}>
              <span className="health-orb"><span /></span>
              <span><strong>{statusLabels[health]}</strong><small>Surveillance active</small></span>
              <button type="button" aria-label="Vérifier l’état de l’API" onClick={checkHealth} className="refresh-button"><Icon name="pulse" size={16} /></button>
            </div>
          </section>

          <section className="metrics-grid" aria-label="Indicateurs d’activité">
            <article className="metric-card">
              <div className="metric-top"><span className="metric-label">ÉTAT DE L’API</span><span className="metric-icon mint"><Icon name="shield" /></span></div>
              <div className={`metric-value status-value ${health}`}>{health === "online" ? "Opérationnelle" : health === "checking" ? "Vérification…" : health === "degraded" ? "Incident en cours" : "Indisponible"}</div>
              <div className="metric-foot"><span className={`tiny-status ${health}`} />{health === "online" ? "Répond normalement" : "Contrôle via /health"}</div>
            </article>
            <article className="metric-card">
              <div className="metric-top"><span className="metric-label">PAIEMENTS ENREGISTRÉS</span><span className="metric-icon violet"><Icon name="credit" /></span></div>
              <div className="metric-value">{transactions.toLocaleString("fr-FR")}<span className="metric-unit"> txn</span></div>
              <div className="metric-foot"><span className="metric-neutral">Total persistant en base de données</span></div>
            </article>
            <article className="metric-card">
              <div className="metric-top"><span className="metric-label">VOLUME TRAITÉ</span><span className="metric-icon blue"><Icon name="arrow" /></span></div>
              <div className="metric-value">{volume.toLocaleString("fr-FR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}<span className="metric-unit"> €</span></div>
              <div className="metric-foot"><span className="metric-neutral">Paiements confirmés uniquement</span></div>
            </article>
          </section>

          <section className={`recovery-summary ${incidentPhase}`} aria-live="polite" aria-label="État de détection et de reprise">
            <div>
              <span className="metric-label">ÉTAPE DE REPRISE</span>
              <strong>{{
                nominal: "Service nominal — en attente d’incident",
                incident_active: "Incident actif — détection en cours",
                detected: "Anomalie ML détectée",
                verifying: "Remédiation exécutée — vérification métier",
                recovered: "Service rétabli et transaction vérifiée",
                recovery_failed: "Reprise non vérifiée — intervention requise",
              }[incidentPhase] || "État de reprise inconnu"}</strong>
            </div>
            <div className="recovery-evidence">
              <span className="metric-label">DERNIÈRE DÉCISION ML</span>
              <strong>{latestDetection
                ? `Anomalie ${latestDetection.actionable ? "actionnable" : "non actionnable"} · score ${Number(latestDetection.anomaly_score).toFixed(3)}`
                : "Aucune anomalie enregistrée"}</strong>
            </div>
          </section>

          <div className="content-grid">
            <section className="panel payment-panel" id="payments">
              <div className="panel-heading">
                <div>
                  <div className="section-kicker">OPÉRATIONS</div>
                  <h2>Effectuer un paiement</h2>
                  <p>Lancez une transaction de démonstration sécurisée.</p>
                </div>
                <span className="panel-heading-icon"><Icon name="wallet" size={20} /></span>
              </div>
              {!token ? (
                <form className="payment-form login-form" onSubmit={loginStep === "username" ? verifyFace : signIn}>
                  <label htmlFor={loginStep === "username" ? "operator-username" : "operator-password"}>Connexion opérateur</label>
                  {loginStep === "username" ? (
                    <>
                      <input id="operator-username" type="text" autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} required placeholder="Identifiant" disabled={isLoggingIn || retrySeconds > 0} />
                      <p className="secure-note">La caméra USB du PC hôte vérifie votre visage avant la saisie du mot de passe.</p>
                    </>
                  ) : (
                    <>
                      <p className="secure-note">Visage reconnu pour <strong>{username}</strong>. Saisissez votre mot de passe.</p>
                      <input id="operator-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required placeholder="Mot de passe" disabled={isLoggingIn} />
                    </>
                  )}
                  {loginError && <p className="form-error" role="alert">{loginError}</p>}
                  {retrySeconds > 0 && <p className="form-error" role="status">Nouvel essai possible dans {retrySeconds} s.</p>}
                  <button className="pay-button" type="submit" disabled={isLoggingIn || retrySeconds > 0}>
                    {isLoggingIn ? loginStep === "username" ? "Vérification faciale…" : "Connexion…" : loginStep === "username" ? "Activer la caméra et vérifier" : "Se connecter"}
                    {!isLoggingIn && <Icon name="arrow" size={16} />}
                  </button>
                  {loginStep === "password" && <button className="signout-button" type="button" onClick={cancelIdentification}>Recommencer l’identification</button>}
                  <div className="secure-note"><Icon name="shield" size={14} />Authentification requise pour consulter les opérations et payer</div>
                </form>
              ) : <form className="payment-form" onSubmit={sendPayment}>
                <label htmlFor="amount">Montant à transférer</label>
                <div className="amount-input-wrap">
                  <span className="currency-symbol">€</span>
                  <input
                    id="amount"
                    type="number"
                    min="0.01"
                    step="0.01"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                    placeholder="0,00"
                    required
                    aria-describedby="payment-hint"
                  />
                  <span className="currency-code">EUR</span>
                </div>
                <div className="payment-details">
                  <span>Compte destinataire</span><strong>•••• •••• •••• 4829</strong>
                </div>
                <button className="pay-button" type="submit" disabled={isPaying}>
                  {isPaying ? <span className="button-spinner" /> : <Icon name="shield" size={17} />}
                  {isPaying ? "Traitement en cours…" : "Confirmer le paiement"}
                  {!isPaying && <Icon name="arrow" size={16} />}
                </button>
                <div className="secure-note" id="payment-hint"><Icon name="check" size={14} />Chaque opération est tracée dans le journal d’événements</div>
              </form>}
            </section>
            {token && role === "admin" && (
              <section className="panel access-panel" aria-label="Gestion des habilitations">
                <div className="panel-heading">
                  <div>
                    <div className="section-kicker">ADMINISTRATION</div>
                    <h2>Habilitations faciales</h2>
                    <p>Créez des comptes, enrôlez les visages depuis la caméra USB du PC hôte ou révoquez un accès.</p>
                  </div>
                  <span className="panel-heading-icon"><Icon name="shield" size={20} /></span>
                </div>
                <form className="access-form" onSubmit={createUser}>
                  <input aria-label="Nouvel identifiant" autoComplete="off" value={newUser.username} onChange={(event) => setNewUser({ ...newUser, username: event.target.value })} placeholder="Nouvel identifiant" required />
                  <input aria-label="Mot de passe temporaire" type="password" autoComplete="new-password" value={newUser.password} onChange={(event) => setNewUser({ ...newUser, password: event.target.value })} placeholder="Mot de passe (12 caractères min.)" minLength={12} required />
                  <select aria-label="Rôle" value={newUser.role} onChange={(event) => setNewUser({ ...newUser, role: event.target.value })}>
                    <option value="operator">Opérateur</option>
                    <option value="admin">Administrateur</option>
                  </select>
                  <button className="pay-button" type="submit" disabled={isManagingUsers}>Créer le compte</button>
                </form>
                {adminError && <p className="form-error" role="status">{adminError}</p>}
                <ul className="access-list">
                  {adminUsers.map((user) => (
                    <li key={user.username}>
                      <span><strong>{user.username}</strong><small>{user.role === "admin" ? "Administrateur" : "Opérateur"} · {user.face_enrolled ? "Visage enrôlé" : "Visage à enrôler"}</small></span>
                      <button type="button" className="signout-button" onClick={() => enrollFace(user.username)} disabled={isManagingUsers}>{user.face_enrolled ? "Réenrôler" : "Enrôler"}</button>
                      {user.username.toLowerCase() !== authenticatedUsername.toLowerCase() && <button type="button" className="signout-button" onClick={() => deleteUser(user.username)} disabled={isManagingUsers}>Révoquer</button>}
                    </li>
                  ))}
                </ul>
              </section>
            )}

            <section className="panel event-panel" id="events">
              <div className="panel-heading event-heading">
                <div>
                  <div className="section-kicker">ACTIVITÉ EN TEMPS RÉEL</div>
                  <h2>Journal d’événements</h2>
                  <p>Les dernières opérations de cette session.</p>
                </div>
                <span className="live-label"><span />EN DIRECT</span>
              </div>
              <div className="event-list" aria-live="polite">
                {events.length === 0 ? (
                  <div className="empty-state">
                    <span className="empty-icon"><Icon name="spark" size={20} /></span>
                    <strong>Tout est calme pour le moment</strong>
                    <span>Les paiements et changements d’état apparaîtront ici.</span>
                  </div>
                ) : events.map((entry) => (
                  <article className={`event-row ${entry.type}`} key={entry.id}>
                    <span className="event-symbol">{entry.type === "success" ? <Icon name="check" size={15} /> : entry.type === "error" ? "!" : <Icon name="clock" size={15} />}</span>
                    <div className="event-copy"><p>{entry.message}</p><time>{entry.time.toLocaleTimeString("fr-FR")}</time></div>
                  </article>
                ))}
              </div>
              <div className="event-panel-footer"><span><span className="footer-live-dot" />Actualisé automatiquement</span><span>{events.length} événement{events.length === 1 ? "" : "s"}</span></div>
            </section>
          </div>

          <section className="panel assistant-panel" id="assistant">
            <div className="panel-heading">
              <div>
                <div className="section-kicker">ASSISTANCE LOCALE · RAG</div>
                <h2>Assistant opérateur</h2>
                <p>Interrogez les procédures et la documentation locale de la plateforme.</p>
              </div>
              <span className="panel-heading-icon"><Icon name="spark" size={20} /></span>
            </div>
            <Assistant token={token} addEvent={addEvent} />
          </section>

          <footer className="page-footer"><span><Icon name="shield" size={14} /> RESILIENCE ALPHA <span className="footer-separator">/</span> CONSOLE DE SUPERVISION</span><span>Connecté à <strong>Payment API</strong><Icon name="arrow" size={12} /></span></footer>
        </div>
      </main>
    </div>
  );
}

function Assistant({ token, addEvent }) {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState([]);
  const [isAsking, setIsAsking] = useState(false);
  const [error, setError] = useState("");

  async function ask(event) {
    event.preventDefault();
    if (!token) {
      setError("Connectez-vous pour interroger l’assistant.");
      return;
    }
    setIsAsking(true);
    setError("");
    try {
      const response = await fetch("/assistant/ask", {
        method: "POST",
        headers: { "Content-Type": "application/json", Authorization: `Bearer ${token}` },
        body: JSON.stringify({ question }),
        signal: AbortSignal.timeout(90000),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || `Assistant indisponible (${response.status}).`);
      setAnswer(result.answer);
      setSources(result.sources || []);
      addEvent("Réponse de l’assistant RAG reçue.", "success");
    } catch (requestError) {
      setError(requestError.message || "Assistant local indisponible.");
      addEvent("L’assistant local n’a pas pu répondre.", "error");
    } finally {
      setIsAsking(false);
    }
  }

  return (
    <form className="assistant-form" onSubmit={ask}>
      <label htmlFor="assistant-question">Question sur l’incident ou les procédures</label>
      <div className="assistant-input-row">
        <input id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ex. Comment vérifier le rétablissement après un incident ?" maxLength={1000} required />
        <button className="assistant-button" type="submit" disabled={isAsking || !token}>
          {isAsking ? "Recherche…" : "Interroger"} <Icon name="arrow" size={15} />
        </button>
      </div>
      {!token && <p className="assistant-hint">Connectez-vous pour accéder à l’assistant local.</p>}
      {isAsking && <p className="assistant-hint">Le modèle local peut nécessiter quelques instants pour répondre.</p>}
      {error && <p className="form-error" role="alert">{error}</p>}
      {answer && <div className="assistant-answer">
        <strong>Réponse documentée</strong>
        <p>{answer}</p>
        {sources.length > 0 && <small>Sources : {sources.join(", ")}</small>}
      </div>}
    </form>
  );
}

createRoot(document.getElementById("root")).render(<App />);

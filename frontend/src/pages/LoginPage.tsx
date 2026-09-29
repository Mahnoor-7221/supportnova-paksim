import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Spinner } from "../components/ui";
import { errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";

const DEMO_ACCOUNTS = [
  { label: "Admin", email: "admin@supportnova.demo", password: "Admin#12345" },
  { label: "Agent", email: "agent@supportnova.demo", password: "Agent#12345" },
  { label: "Customer", email: "customer@supportnova.demo", password: "Customer#12345" },
];

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function fillDemo(account: (typeof DEMO_ACCOUNTS)[number]) {
    setEmail(account.email);
    setPassword(account.password);
    setError("");
  }

  return (
    <div className="nova-login-shell">
      <div className="nova-login-orbit nova-login-orbit-one" />
      <div className="nova-login-orbit nova-login-orbit-two" />
      <Link to="/" className="nova-login-brand" style={{ textDecoration: "none" }}>
        <span className="nova-mark">✦</span>
        <span><strong>SupportNova</strong><small>Trust &amp; Resolution</small></span>
      </Link>

      <div className="nova-login-layout">
        <section className="nova-login-intro">
          <span className="nova-kicker">AI complaint intelligence</span>
          <h1>Good decisions need<br /><em>trusted intelligence.</em></h1>
          <p>SupportNova brings AI analysis, independent validation and human oversight into one calm, transparent workspace.</p>
          <div className="nova-feature-row">
            <span>✦ Generate</span><span>◌ Verify</span><span>◇ Explain</span><span>✧ Protect</span>
          </div>
          <div className="nova-login-quote">“AI can move quickly. Governance makes sure it moves wisely.”</div>
        </section>

        <section className="nova-login-card">
          <div className="nova-login-card-head">
            <span className="nova-mini-orb">N</span>
            <div><h2>Welcome back</h2><p>Enter your details to continue.</p></div>
          </div>
          <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="label" htmlFor="login-email">Email</label>
              <input id="login-email" type="email" required autoComplete="email" className="input mt-1" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@supportnova.demo" />
            </div>
            <div>
              <label className="label" htmlFor="login-password">Password</label>
              <input id="login-password" type="password" required autoComplete="current-password" className="input mt-1" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" />
            </div>
            {error && <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
            <button type="submit" className="btn btn-primary w-full" disabled={busy}>
              {busy && <Spinner className="h-4 w-4 text-white" />}
              {busy ? "Signing in…" : "Enter SupportNova →"}
            </button>
          </form>
          <div className="nova-demo-area">
            <p className="label">Quick demo access</p>
            <div className="mt-2 grid grid-cols-3 gap-2">
              {DEMO_ACCOUNTS.map((account) => (
                <button key={account.label} type="button" className="btn btn-secondary btn-sm" onClick={() => fillDemo(account)}>{account.label}</button>
              ))}
            </div>
            <p className="mt-2 text-xs text-slate-400">Choose a role to fill its demo credentials, then sign in.</p>
          </div>
          <p className="mt-4 text-center text-sm text-slate-500">
            New to PakSim? <Link to="/signup" className="font-medium text-[var(--nova-forest)]">Create an account</Link>
          </p>
        </section>
      </div>
      <footer className="nova-login-footer"><span>Built for transparent AI-assisted resolution</span><span>Human governed · Secure · Traceable</span></footer>
    </div>
  )
}

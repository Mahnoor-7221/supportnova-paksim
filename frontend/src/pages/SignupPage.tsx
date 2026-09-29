import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Spinner } from "../components/ui";
import { errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";

export default function SignupPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("Password must be at least 8 characters.");
      return;
    }
    if (password !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setBusy(true);
    try {
      await register(fullName.trim(), email.trim(), password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="nova-login-shell">
      <div className="nova-login-orbit nova-login-orbit-one" />
      <div className="nova-login-orbit nova-login-orbit-two" />
      <header className="nova-login-brand">
        <span className="nova-mark">✦</span>
        <span><strong>PakSim</strong><small>Customer Support</small></span>
      </header>

      <div className="nova-login-layout">
        <section className="nova-login-intro">
          <span className="nova-kicker">Create your account</span>
          <h1>Get help in<br /><em>seconds, not queues.</em></h1>
          <p>Create a free PakSim account to chat with Nova, our AI support assistant, track complaints and manage your SIM issues -- in Roman Urdu, Urdu or English.</p>
          <div className="nova-feature-row">
            <span>✦ Instant answers</span><span>◌ Case tracking</span><span>◇ Any language</span>
          </div>
        </section>

        <section className="nova-login-card">
          <div className="nova-login-card-head">
            <span className="nova-mini-orb">N</span>
            <div><h2>Create account</h2><p>It only takes a minute.</p></div>
          </div>
          <form className="mt-7 space-y-4" onSubmit={handleSubmit}>
            <div>
              <label className="label" htmlFor="signup-name">Full name</label>
              <input id="signup-name" type="text" required autoComplete="name" className="input mt-1" value={fullName} onChange={(event) => setFullName(event.target.value)} placeholder="Your full name" />
            </div>
            <div>
              <label className="label" htmlFor="signup-email">Email</label>
              <input id="signup-email" type="email" required autoComplete="email" className="input mt-1" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@example.com" />
            </div>
            <div>
              <label className="label" htmlFor="signup-password">Password</label>
              <input id="signup-password" type="password" required minLength={8} autoComplete="new-password" className="input mt-1" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" />
            </div>
            <div>
              <label className="label" htmlFor="signup-confirm">Confirm password</label>
              <input id="signup-confirm" type="password" required minLength={8} autoComplete="new-password" className="input mt-1" value={confirm} onChange={(event) => setConfirm(event.target.value)} placeholder="Re-enter password" />
            </div>
            {error && <p className="rounded-xl border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>}
            <button type="submit" className="btn btn-primary w-full" disabled={busy}>
              {busy && <Spinner className="h-4 w-4 text-white" />}
              {busy ? "Creating account…" : "Create account →"}
            </button>
          </form>
          <p className="mt-4 text-center text-sm text-slate-500">
            Already have an account? <Link to="/login" className="font-medium text-[var(--nova-forest)]">Sign in</Link>
          </p>
        </section>
      </div>
      <footer className="nova-login-footer"><span>Built for transparent AI-assisted resolution</span><span>Human governed · Secure · Traceable</span></footer>
    </div>
  );
}

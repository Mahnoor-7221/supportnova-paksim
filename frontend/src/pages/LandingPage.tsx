import { Link } from "react-router-dom";
import { useState } from "react";
import DemoVideo from "../components/DemoVideo";
import PublicLayout from "../components/PublicLayout";
import PolicyBrowser, { POLICY_COUNT } from "../components/PolicyBrowser";
import { FEATURES, OFFER_BANNERS, PLANS, STEPS } from "../data/publicContent";

const POLICIES = [
  {
    icon: "🪪",
    title: "SIM registration & ownership",
    body: "Every SIM is registered against your original CNIC through biometric verification, in line with PTA regulations. Only the registered owner (or someone with verified consent) can request a replacement, block, or port.",
  },
  {
    icon: "🔐",
    title: "OTP, PIN & password safety",
    body: "PakSim staff and Nova AI will never ask you to share an OTP, PIN, password, or full card/bank number. Anyone asking for these is not from PakSim — do not share them.",
  },
  {
    icon: "🚨",
    title: "Lost, stolen or snatched SIM",
    body: "Report immediately so we can temporarily block the number. File an FIR, then visit a PakSim franchise with your original CNIC for a duplicate. Treated as priority (P1).",
  },
  {
    icon: "💳",
    title: "Billing, recharge & refunds",
    body: "Recharge and balance disputes are verified against transaction records. Approved corrections are credited within 24–48 hours. Keep your reference ID ready.",
  },
  {
    icon: "📶",
    title: "Fair usage & network",
    body: "Packages follow the fair-usage limits shown at purchase. Coverage issues are logged with area details and routed to our technical team when self-help doesn't resolve them.",
  },
  {
    icon: "🛡️",
    title: "Privacy & data protection",
    body: "Your personal and usage data is used only to provide service, verify identity, and resolve complaints. Never sold. Access limited to authorised, logged staff.",
  },
];

export default function LandingPage() {
  const [showAll, setShowAll] = useState(false);

  return (
    <PublicLayout>
      <section className="lp-hero pp-hero">
        <span className="pp-float pp-float-1">✦</span>
        <span className="pp-float pp-float-2">◈</span>
        <div className="lp-hero-copy">
          <span className="lp-badge">
            <span className="lp-badge-dot" />
            AI-powered · PTA-aligned · 24/7
          </span>
          <h1>
            Real help,<br />
            in <em>your own words.</em>
          </h1>
          <p className="lp-hero-lead">
            Nova understands Roman Urdu, Urdu and English. Tell it about your SIM, balance or
            internet and get a clear answer. Serious issues go to humans with a trackable complaint number.
          </p>
          <div className="lp-hero-cta">
            <Link to="/signup" className="btn btn-primary lp-btn-lg">Create free account →</Link>
            <Link to="/login" className="btn btn-secondary lp-btn-lg">Login</Link>
          </div>
          <div className="lp-trust-row">
            <span>✓ No OTP ever asked</span>
            <span>✓ Human oversight</span>
            <span>✓ Full complaint tracking</span>
          </div>
        </div>
        <div className="lp-hero-card">
          <div className="lp-chat-preview">
            <div className="lp-chat-head">
              <span className="lp-chat-avatar">N</span>
              <div>
                <strong>Nova</strong>
                <small>Online · Ready to help</small>
              </div>
            </div>
            <div className="lp-chat-body">
              <div className="lp-bubble lp-bubble-ai">
                Assalam o Alaikum! Main Nova hoon. Aap ka SIM, balance ya account issue
                bataiye — English, Urdu ya Roman Urdu mein.
              </div>
              <div className="lp-bubble lp-bubble-user">
                Meri SIM kaam nahi kar rahi, network nahi aa raha
              </div>
              <div className="lp-bubble lp-bubble-ai">
                Samajh gaya. Pehle ye check karein:<br />
                <strong>1.</strong> Airplane mode on/off karein<br />
                <strong>2.</strong> Phone restart karein<br />
                <strong>3.</strong> Agar ab bhi issue ho to main complaint bana dunga
              </div>
            </div>
            <div className="lp-chat-foot">
              <span className="lp-typing">Nova is typing…</span>
            </div>
          </div>
        </div>
      </section>

      <section id="walkthrough" className="lp-section lp-video-section">
        <div className="lp-section-head">
          <span className="lp-kicker">Watch how it works</span>
          <h2>Customer journey at a glance</h2>
          <p>Login se Nova AI chat, complaint tracking aur chat history tak, poora flow ek short video mein.</p>
        </div>
        <div className="lp-video-wrap">
          <DemoVideo />
        </div>
      </section>

      <section id="plans" className="lp-section">
        <div className="lp-section-head">
          <span className="lp-kicker">Plans &amp; Offers</span>
          <h2>PakSim plans, simple and clear</h2>
          <p>Sample of our packages. Final price and terms are always shown before you order.</p>
        </div>
        <div className="pp-plans">
          {PLANS.map((pl, i) => (
            <article key={pl.code} className={`pp-plan pp-tone-${pl.tone} ${"featured" in pl ? "is-featured" : ""}`} style={{ animationDelay: `${i * 0.6}s` }}>
              <span className="pp-plan-tag">{pl.tag}</span>
              <h3>{pl.name}</h3>
              <div className="pp-plan-price"><small>Rs.</small>{pl.price}</div>
              <small className="pp-plan-valid">Valid {pl.validity}</small>
              <ul>{pl.perks.map((x) => <li key={x}>{x}</li>)}</ul>
              <Link to="/signup" className="pp-plan-btn">Get started</Link>
            </article>
          ))}
        </div>
        <div className="pp-banners">
          {OFFER_BANNERS.map((b) => (
            <div key={b.title} className="pp-banner">
              <span>{b.icon}</span>
              <div><strong>{b.title}</strong><p>{b.text}</p></div>
            </div>
          ))}
        </div>
      </section>

      <section id="how-it-works" className="lp-section lp-section-alt">
        <div className="lp-section-head">
          <span className="lp-kicker">How it works</span>
          <h2>Four clear steps</h2>
        </div>
        <div className="pp-steps">
          {STEPS.map((st) => (
            <div key={st.num} className="pp-step">
              <span className="lp-step-num">{st.num}</span>
              <strong>{st.title}</strong>
              <p>{st.desc}</p>
            </div>
          ))}
        </div>
        <div className="lp-steps-cta">
          <Link to="/how-it-works" className="btn btn-secondary">Full flow: customer to resolution →</Link>
        </div>
      </section>

      <section id="features" className="lp-section">
        <div className="lp-section-head">
          <span className="lp-kicker">Why PakSim + Nova</span>
          <h2>Built for real customers</h2>
        </div>
        <div className="lp-features">
          {FEATURES.slice(0, 6).map((f) => (
            <div key={f.title} className="lp-feature-card pp-float-card">
              <span className="lp-feature-icon">{f.icon}</span>
              <strong>{f.title}</strong>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
        <div className="lp-steps-cta">
          <Link to="/features" className="btn btn-secondary">See all features →</Link>
        </div>
      </section>

      <section id="policies" className="lp-section lp-section-alt">
        <div className="lp-section-head">
          <span className="lp-kicker">Policies &amp; how we work</span>
          <h2>Transparent rules before you sign up</h2>
          <p>A short preview. All {POLICY_COUNT}+ policies are available below or on the policies page.</p>
        </div>
        <div className="lp-policies">
          {POLICIES.map((p) => (
            <div key={p.title} className="lp-policy-card">
              <span className="lp-policy-icon">{p.icon}</span>
              <h3>{p.title}</h3>
              <p>{p.body}</p>
            </div>
          ))}
        </div>
        <div className="lp-steps-cta">
          <button type="button" className="btn btn-primary" aria-expanded={showAll} aria-controls="all-policies" onClick={() => setShowAll((v) => !v)}>
            {showAll ? "Hide all policies ▲" : `Browse all ${POLICY_COUNT}+ policies ▼`}
          </button>
          <Link to="/policies" className="btn btn-secondary">Open policies page →</Link>
        </div>
        {showAll && (
          <div id="all-policies" className="pp-collapse">
            <PolicyBrowser compact />
          </div>
        )}
      </section>

      <section className="lp-final-cta">
        <div className="lp-final-inner">
          <h2>Ready to get real help?</h2>
          <p>Create a free account in under a minute, or try the demo Customer login and talk to Nova right away.</p>
          <div className="lp-hero-cta">
            <Link to="/signup" className="btn btn-primary lp-btn-lg">Create free account →</Link>
            <Link to="/login" className="btn btn-secondary lp-btn-lg">Login with demo</Link>
          </div>
        </div>
      </section>
    </PublicLayout>
  );
}

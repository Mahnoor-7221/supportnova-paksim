import { Link } from "react-router-dom";
import PublicLayout from "../components/PublicLayout";
import { FLOW } from "../data/publicContent";

export default function HowItWorksPage() {
  return (
    <PublicLayout>
      <section className="lp-section pp-page-head">
        <span className="lp-kicker">How it works</span>
        <h1>From your message to a resolution</h1>
        <p>Customer → Nova → self-service or complaint → agent → admin → resolution.</p>
      </section>
      <section className="lp-section pp-page-body">
        <ol className="pp-flow">
          {FLOW.map((s, i) => (
            <li key={s.title} className="pp-flow-item">
              <span className="pp-flow-num">{i + 1}</span>
              <div className="pp-flow-card">
                <span className="pp-chip pp-chip-gold">{s.who}</span>
                <h3>{s.title}</h3>
                <p>{s.text}</p>
                <small>{s.note}</small>
              </div>
            </li>
          ))}
        </ol>
        <div className="lp-steps-cta">
          <Link to="/login" className="btn btn-primary">Try the demo Customer →</Link>
          <Link to="/features" className="btn btn-secondary">See all features</Link>
        </div>
      </section>
    </PublicLayout>
  );
}

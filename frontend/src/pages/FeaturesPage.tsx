import { Link } from "react-router-dom";
import PublicLayout from "../components/PublicLayout";
import { FEATURES } from "../data/publicContent";

export default function FeaturesPage() {
  return (
    <PublicLayout>
      <section className="lp-section pp-page-head">
        <span className="lp-kicker">Features</span>
        <h1>Everything PakSim + Nova gives you</h1>
        <p>From instant AI guidance to agent and admin tools that keep every case traceable.</p>
      </section>
      <section className="lp-section pp-page-body">
        <div className="pp-feature-grid">
          {FEATURES.map((f) => (
            <div key={f.title} className="lp-feature-card pp-float-card">
              <span className="lp-feature-icon">{f.icon}</span>
              <strong>{f.title}</strong>
              <p>{f.text}</p>
            </div>
          ))}
        </div>
        <div className="lp-steps-cta">
          <Link to="/signup" className="btn btn-primary">Create free account →</Link>
          <Link to="/policies" className="btn btn-secondary">Browse policies</Link>
        </div>
      </section>
    </PublicLayout>
  );
}

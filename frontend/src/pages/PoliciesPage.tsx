import { Link } from "react-router-dom";
import PublicLayout from "../components/PublicLayout";
import PolicyBrowser, { POLICY_COUNT } from "../components/PolicyBrowser";

export default function PoliciesPage() {
  return (
    <PublicLayout>
      <section className="lp-section pp-page-head">
        <span className="lp-kicker">Policies &amp; guidance</span>
        <h1>{POLICY_COUNT}+ support policies, in plain language</h1>
        <p>
          General guidance that matches the approved knowledge Nova uses. Where a request is
          sensitive, Nova hands it to a human agent instead of guessing.
        </p>
      </section>
      <section className="lp-section pp-page-body">
        <PolicyBrowser />
        <div className="lp-steps-cta">
          <Link to="/signup" className="btn btn-primary">Ask Nova about your case →</Link>
          <Link to="/how-it-works" className="btn btn-secondary">See how it works</Link>
        </div>
      </section>
    </PublicLayout>
  );
}

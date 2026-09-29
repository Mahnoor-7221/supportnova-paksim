export const PLANS = [
  { code: "PKG-DAILY-1GB", tag: "Daily", name: "Daily 1GB", price: 50, validity: "1 day", perks: ["1 GB data"], tone: "sage" },
  { code: "PKG-WEEK-5GB", tag: "Weekly", name: "Weekly 5GB", price: 250, validity: "7 days", perks: ["5 GB data"], tone: "gold" },
  { code: "PKG-MONTH-15GB", tag: "Monthly", name: "Monthly 15GB Super", price: 800, validity: "30 days", perks: ["15 GB data", "500 minutes", "500 SMS"], tone: "forest", featured: true },
  { code: "PKG-HYBRID-PRO", tag: "Monthly", name: "Hybrid Pro 20GB", price: 1200, validity: "30 days", perks: ["20 GB data", "1000 minutes", "1000 SMS"], tone: "ink" },
] as const;

export const OFFER_BANNERS = [
  { icon: "✦", title: "Nova support, always on", text: "Get guided help for SIM, balance and internet issues in your own language." },
  { icon: "◈", title: "Track every complaint", text: "Follow status and timeline from Nova to agent to resolution." },
  { icon: "◎", title: "Safe by design", text: "No OTP, PIN or password is ever requested by PakSim or Nova." },
];

export const FEATURES = [
  { icon: "✦", title: "24/7 Nova AI chat", text: "Instant guidance from approved policies, any time of day." },
  { icon: "◌", title: "Multilingual", text: "English, Urdu, Roman Urdu and Sindhi supported." },
  { icon: "◇", title: "Voice input", text: "Speak your issue where your device supports it." },
  { icon: "✧", title: "Human escalation", text: "Sensitive or unsupported requests go to a human agent." },
  { icon: "◈", title: "Complaint tracking", text: "Status, timeline and service level for every case." },
  { icon: "◎", title: "Security first", text: "OTP/PIN masking, injection guards and a full audit trail." },
  { icon: "▣", title: "Approved knowledge only", text: "Nova answers from approved policies and rules, not guesses." },
  { icon: "⌘", title: "SIMs, packages & orders", text: "Manage SIMs, browse packages and see your orders." },
  { icon: "☰", title: "Agent workspace", text: "Agents get a case room, evidence and suggested next steps." },
  { icon: "▤", title: "Admin oversight", text: "Admins manage users, agents, categories, rules and audit logs." },
  { icon: "⟲", title: "Chat history", text: "Review your past Nova conversations any time." },
  { icon: "✓", title: "Manual review queue", text: "Reviewers check flagged answers before they reach customers." },
];

export const FLOW = [
  { who: "Customer", title: "Describes the issue", text: "Signs in and tells Nova the problem in English, Urdu, Roman Urdu or Sindhi.", note: "Never asked for OTP, PIN or password." },
  { who: "Nova", title: "Understands and checks approved knowledge", text: "Nova classifies the request and looks up approved policies and rules.", note: "Unsupported answers are not invented." },
  { who: "Nova", title: "Self-service answer or complaint", text: "If guidance solves it, the customer is done. Otherwise Nova files a trackable complaint.", note: "Sensitive cases (lost SIM, fraud) escalate automatically." },
  { who: "Agent", title: "Reviews and works the case", text: "An agent opens the case room, reviews evidence and follows the approved rule matrix.", note: "Can request more details from the customer." },
  { who: "Admin", title: "Oversees quality and rules", text: "Admins manage categories, rules, agents and audit logs, and handle escalations.", note: "Every action is recorded." },
  { who: "Resolution", title: "Customer is updated", text: "The customer sees the outcome and timeline, and can give feedback or reopen.", note: "Feedback improves the guidance." },
];

export const STEPS = [
  { num: "01", title: "Create account or Login", desc: "Sign up with your email, or use the demo Customer account to try instantly." },
  { num: "02", title: "Open Nova AI chat", desc: "After login, Nova is ready 24/7 in English, Urdu, Roman Urdu or Sindhi." },
  { num: "03", title: "Tell your issue naturally", desc: "Write like you talk: “Meri SIM kaam nahi kar rahi”." },
  { num: "04", title: "Get an answer or a complaint", desc: "Clear steps from approved policy, or a trackable complaint when needed." },
];

# Customer portal UI update

Updated the existing PakSim customer portal without rebuilding it from scratch.

- One customer navigation only; the old secondary Dashboard/My SIMs/Packages/Orders row was removed from customer pages.
- Customer navigation now uses **Activity** instead of the e-commerce-style **Orders** label.
- Activity keeps SIM purchases, package activations, replacements and payment references.
- Packages now use a PakSim-native card marketplace and a 3-step SIM → payment → confirmation flow.
- My SIMs now use a registration/delivery/review flow for new SIMs and clear lost/stolen/damaged + replacement flows.
- Replacement keeps the same phone number and issues a new SIM/ICCID through the existing backend endpoint.
- Services is a dedicated telecom services hub, not a second navigation system.
- Nova has a stronger visual identity, speaking indicator, Voice ON/OFF and Stop controls, plus per-message Read Aloud.
- Complaint pages retain the existing backend workflow while using customer-friendly status/timeline presentation.

Validation:
- Backend compile: passed.
- Backend tests with PYTHONPATH=.: 9 passed.
- Frontend build could not be executed because this environment has no installed frontend dependencies and `npm ci` timed out; no claim of a successful production frontend build is made.

# Proposal-to-prototype mapping

| Proposal area | Prototype implementation | Boundary |
|---|---|---|
| CEIR national registry | Device registry and list status | Local SQLite demo records |
| White/grey/black lists | Device status workflow | No operator enforcement |
| TAC validation | Local TAC registry + Luhn check | No GSMA database access |
| BLO exception | Exact IMEI–IMSI exception record | Demo metadata only |
| Distributed EIR | Operator nodes and sync acknowledgements | Simulated; no network links |
| 2G/3G/4G/5G | RAT field in synthetic events | No MAP, S13 or N5g-EIR protocol |
| Clone detection | Time/distance conflict heuristic | Synthetic events; alert-only |
| Duplicate resolution | Dispute management and BLO | Manual workflow prototype |
| Law enforcement | Warrant ID, court, officer and supervisor approval | No live location or subscriber query |
| Immutable audit | SHA-256 hash-linked records | Application-level tamper evidence, not WORM/HSM |
| Analytics | Counts, alerts and CSV export | Small local dataset |
| RBAC | Six proposal-aligned roles | Demo authentication; no MFA/SSO |
| Privacy and retention | Data-minimizing synthetic sample fields | Retention automation and DPIA remain Phase 1 work |
| Implementation roadmap | Five-phase mapping in this document | Procurement and operator deployment not included |

## Proposal decision gates retained

Phase 1 legal alignment, DPIA, stakeholder agreements and interface specification
must precede real production build. The prototype is not evidence of compliance
with GSMA, ITU-T, 3GPP, national telecom law or data-protection law.

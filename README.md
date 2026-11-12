# National CEIR — IMEI Device Tracking & Management Prototype

A runnable educational/stakeholder-review prototype based on the uploaded
**National IMEI-Based Device Tracking and Management System** proposal.

## Important scope and safety boundary

This is a **simulation/prototype**, not a production national telecom system.
It uses synthetic device/network-event data. It does not connect to mobile
operator cores, GSMA systems, SS7, Diameter S13, 5G N5g-EIR, live CDR feeds,
GPS, subscriber databases, or real law-enforcement systems. It cannot locate
or track real people or phones. The EIR synchronization and clone-detection
features are simulated with local demo records.

Before any real deployment, obtain legal authorization, complete a DPIA,
commission an independent security review, establish operator agreements,
and implement certified interfaces with participating operators and relevant
standards bodies. Do not use the demo credentials in production.

## Features

- CEIR overview dashboard and device inventory
- IMEI/IMEISV format checks and Luhn check-digit validation
- TAC registry (local demonstration registry only; not a GSMA feed)
- White, grey and black list management
- Blacklist Override (BLO) for an exact IMEI–IMSI pair
- Operator EIR nodes and simulated synchronization/acknowledgements
- Synthetic attach-event ingestion and time/distance clone-anomaly demo
- Warrant-gated law-enforcement case workflow with supervisor approval
- Tamper-evident, hash-chained audit events
- Device dispute workflow
- CSV report export
- Role-based access control and password hashing
- Demo data and automated tests

## Requirements

- Python 3.10+
- pip

## Run on Windows

```powershell
cd National_CEIR_Project
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

## Run on Linux/macOS

```bash
cd National_CEIR_Project
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000

On first run the SQLite database is created and populated with fictional
records and demo accounts.

## Demo accounts

All demo accounts use password `ChangeMe123!`:

| Username | Role | Purpose |
|---|---|---|
| `admin` | Regulator Administrator | Full prototype administration |
| `analyst` | Regulator Analyst | Registry, lists, analytics |
| `operator` | Operator Liaison | EIR simulation and device review |
| `officer` | Law Enforcement Officer | Submit warrant-backed case |
| `supervisor` | Law Enforcement Supervisor | Approve sensitive cases |
| `auditor` | Data Protection Auditor | Read-only audit review |

Change these credentials immediately in any shared demonstration. This
prototype intentionally has no public registration.

## Main workflows

1. Sign in as `admin` or `analyst`.
2. Add a device from **Devices**. Use a valid 15-digit IMEI; the form checks
   the Luhn digit and local TAC registry.
3. Change list status from the device detail page.
4. Use **EIR Nodes** to simulate synchronization to operator-side copies.
5. Add synthetic attach events and run the clone-anomaly demonstration.
6. Sign in as `officer` to submit a tracking-related case with a warrant ID.
   The case remains pending until a `supervisor` approves it.
7. Review the audit chain under **Audit Log**.

## Production gaps (not implemented)

- Real GSMA TAC/IMEI database licensing and integration
- Certified 2G/3G MAP, 4G Diameter S13 and 5G N5g-EIR interfaces
- Operator-grade HA active-active deployment and geo-replication
- Real-time CDR/attach feed ingestion
- Real identity proofing, judiciary warrant registry integration and MFA
- Production key management, HSM-backed signing, immutable external log storage
- Statutory retention/deletion automation and DPIA/legal sign-off
- Citizen portal, customs/import integration and international data-sharing agreements

The proposal itself calls for Phase 1 legal alignment and stakeholder
formalization before full build. This prototype is suitable for demonstrating
workflows and gathering requirements, not for enforcement.

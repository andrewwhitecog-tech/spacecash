# SpaceCash Legal And Compliance Gate

Current reviewer handoff packet: `LEGAL_COMPLIANCE_REVIEWER_HANDOFF_2026-06-10.md`.

This file is not legal advice. It defines the review evidence required before
real-money or public mainnet use.

## Required Review

- Token/payment classification.
- Supply, distribution, treasury, fee, and burn policy.
- Genesis allocation basis, verifier output, allocation hash, and devnet
  migration boundary.
- Consumer protection and refund terms.
- Tax treatment and reporting responsibilities.
- Restricted-product controls.
- Customer support workflow.
- Data retention and privacy policy.
- Marketing and risk disclosures.
- Jurisdictional availability.

## Required Evidence

- Written reviewer name or firm.
- Reviewed source hash and release bundle hash.
- Reviewed genesis allocation hash and verifier output.
- Approved use case.
- Prohibited use cases.
- Required disclosures.
- Required operational controls.
- Final approval or explicit no-launch decision.

## Evidence Command

Generate and verify the machine-readable template:

```powershell
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --template-out _tmp\spacecash_legal_compliance_evidence_template.json
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --verify _tmp\spacecash_legal_compliance_evidence_template.json
```

Generate the reviewer workbench packet:

```powershell
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --workbench-out-dir _tmp\spacecash_legal_compliance_workbench --force
```

Before real-money or mainnet use, the completed file must pass:

```powershell
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --verify _tmp\spacecash_legal_compliance_evidence.json --require-complete
```

The workbench writes `legal_compliance_evidence_workbench.json`,
`legal_compliance_evidence_workbench_check.json`, area workpapers, draft policy
documents, final-decision template, and `SHA256SUMS.txt`. These are preparation
artifacts only; the legal/compliance manual gate remains blocked until a final
reviewer-completed evidence file passes `--require-complete`.

## Launch Rule

If this gate is not signed off, SpaceCash must remain described as a local
signed devnet and must not be presented as mainnet, investment product,
exchange-listed asset, or legal tender.

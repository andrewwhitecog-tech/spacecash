# SpaceCash Manual Gates

These gates cannot be completed by code alone. They require human review,
evidence, and signoff before SpaceCash can move from local signed devnet to any
mainnet or real-money use.

## Required Evidence

| Gate | Status | Required evidence |
| --- | --- | --- |
| Public testnet | Blocked | Reproducible node setup, monitored bootstrap peers, multiple independent nodes, testnet incident log, and final testnet report. |
| External security review | Blocked | Security-review packet, consensus spec hash, monetary policy hash, signed audit scope, reviewed commit/source hash, findings log, remediation tracker, remediation evidence, and auditor closure. |
| Legal/compliance review | Blocked | Written review for token/payment use, supply/distribution policy, machine-verified genesis allocation basis, treasury controls, fee/burn policy, tax handling, restricted-product policy, customer support, refunds, and terms. |
| Wallet recovery/custody policy | Blocked | Wallet policy hash, recovery standard, final address versioning, backup rotation, lost-key guidance, compromised-key guidance, and custody/hardware plan. |
| Production deployment runbook | Blocked | Reproducible deployment, monitored release process, rollback procedure, incident response, and archived release bundle. |

Generate the machine-readable evidence template with:

```powershell
python tools\spacecash_gate_evidence.py --template-out _tmp\spacecash_manual_gate_evidence_template.json
python tools\spacecash_gate_evidence.py --verify _tmp\spacecash_manual_gate_evidence_template.json
python tools\spacecash_public_testnet_evidence.py --template-out _tmp\spacecash_public_testnet_evidence_template.json
python tools\spacecash_public_testnet_evidence.py --verify _tmp\spacecash_public_testnet_evidence_template.json
python tools\spacecash_security_review_evidence.py --template-out _tmp\spacecash_security_review_evidence_template.json
python tools\spacecash_security_review_evidence.py --verify _tmp\spacecash_security_review_evidence_template.json
python tools\spacecash_legal_compliance_evidence.py --template-out _tmp\spacecash_legal_compliance_evidence_template.json
python tools\spacecash_legal_compliance_evidence.py --verify _tmp\spacecash_legal_compliance_evidence_template.json
python tools\spacecash_wallet_custody_evidence.py --template-out _tmp\spacecash_wallet_custody_evidence_template.json
python tools\spacecash_wallet_custody_evidence.py --verify _tmp\spacecash_wallet_custody_evidence_template.json
python tools\spacecash_production_deployment_evidence.py --template-out _tmp\spacecash_production_deployment_evidence_template.json
python tools\spacecash_production_deployment_evidence.py --verify _tmp\spacecash_production_deployment_evidence_template.json
python tools\spacecash_mainnet_decision.py --template-out _tmp\spacecash_mainnet_decision_template.json
python tools\spacecash_mainnet_decision.py --verify _tmp\spacecash_mainnet_decision_template.json
```

Before any mainnet claim, the completed evidence file must pass:

```powershell
python tools\spacecash_gate_evidence.py --verify _tmp\spacecash_manual_gate_evidence.json --require-complete
python tools\spacecash_public_testnet_evidence.py --verify _tmp\spacecash_public_testnet_evidence.json --require-complete
python tools\spacecash_security_review_evidence.py --verify _tmp\spacecash_security_review_evidence.json --require-complete
python tools\spacecash_legal_compliance_evidence.py --verify _tmp\spacecash_legal_compliance_evidence.json --require-complete
python tools\spacecash_wallet_custody_evidence.py --verify _tmp\spacecash_wallet_custody_evidence.json --require-complete
python tools\spacecash_production_deployment_evidence.py --verify _tmp\spacecash_production_deployment_evidence.json --require-complete
python tools\spacecash_mainnet_decision.py --verify _tmp\spacecash_mainnet_decision.json --require-complete
```

## Bundle Review Rule

A release bundle is reviewable only when:

- `SHA256SUMS.txt` verifies all artifacts.
- `release_manifest.json` has `checks_ok: true`.
- `candidate_summary.json` has no automated readiness blockers.
- `security_review/SHA256SUMS.txt` verifies the external-review preparation packet.
- `monetary_policy.json` is archived and its policy hash matches the live protocol config.
- `genesis_plan.json` is archived and its plan hash matches the live protocol config.
- `genesis_allocation_template.json` and `genesis_allocation_check.json` are archived; any launch allocation must pass `--require-approved`.
- `manual_gate_evidence_template.json` and `manual_gate_evidence_check.json` are archived; any launch claim must pass `--require-complete`.
- `public_testnet_evidence_template.json` and `public_testnet_evidence_check.json` are archived; the public testnet gate must pass `--require-complete`.
- `security_review_evidence_template.json` and `security_review_evidence_check.json` are archived; the external security review gate must pass `--require-complete`.
- `legal_compliance_evidence_template.json` and `legal_compliance_evidence_check.json` are archived; the legal/compliance gate must pass `--require-complete`.
- `wallet_custody_evidence_template.json` and `wallet_custody_evidence_check.json` are archived; the wallet recovery/custody gate must pass `--require-complete`.
- `production_deployment_evidence_template.json` and `production_deployment_evidence_check.json` are archived; the production deployment gate must pass `--require-complete`.
- `mainnet_decision_template.json` and `mainnet_decision_check.json` are archived; the final decision file must pass `--require-complete`.
- `wallet_policy.json` is archived and its policy hash matches the live protocol config.
- Manual gate documents are included in `docs/spacecash`.
- The final source hash is archived with reviewer signoff.

## Mainnet Rule

`mainnet_ready` must remain false until all gates above have evidence and
signoff, and `tools\spacecash_mainnet_decision.py --require-complete` passes
against the final approved decision file. A clean candidate ledger only proves
automated readiness; it is not a launch authorization.

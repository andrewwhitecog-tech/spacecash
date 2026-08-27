# SpaceCash Security Audit Scope

Current auditor handoff packet: `SECURITY_REVIEW_AUDITOR_HANDOFF_2026-06-10.md`.

## Scope

- `spacecash_core.protocol`
- `spacecash_core.ledger.SpaceCashLedger`
- `tools/spacecash_consensus_spec.py`
- `tools/spacecash_monetary_policy.py`
- `tools/spacecash_genesis_allocation.py`
- `tools/spacecash_genesis_plan.py`
- `tools/spacecash_daemon.py`
- `tools/spacecash_cli.py`
- `tools/spacecash_candidate.py`
- `tools/spacecash_gate_evidence.py`
- `tools/spacecash_public_testnet_evidence.py`
- `tools/spacecash_security_review_evidence.py`
- `tools/spacecash_legal_compliance_evidence.py`
- `tools/spacecash_wallet_custody_evidence.py`
- `tools/spacecash_production_deployment_evidence.py`
- `tools/spacecash_mainnet_decision.py`
- `tools/spacecash_release_manifest.py`
- `tools/spacecash_release_bundle.py`
- `tools/spacecash_security_review_packet.py`
- `tools/spacecash_wallet_policy.py`
- Browser wallet signing and encrypted backup flows in `app.py`
- Product-payment and receipt lifecycle
- Peer manifest, snapshot verification, fork-choice, and guarded import paths

## Required Review Topics

- Signature verification, payload binding, replay protection, and nonce rules.
- Balance accounting, total supply invariant, and transaction-to-block linkage.
- Block hash, merkle root, producer seal, producer allowlist, and versioning.
- Consensus spec hash, append-only fork choice, and non-reorg policy.
- Monetary policy hash, fixed supply invariant, treasury/faucet boundary, and
  absence of mint routes.
- Genesis plan hash, devnet migration boundary, candidate key exclusion, and
  allocation total review.
- Genesis allocation schema enforcement, allocation hash reproduction,
  duplicate-address rejection, exact supply total, and approval-gate behavior.
- Validator registration, checkpoint payloads, quorum rules, and vote audit.
- Peer discovery, snapshot verification, append-only import, backup, and
  rollback behavior.
- Wallet backup encryption, passphrase risk, key loss, and custody boundaries.
- Wallet policy hash, address versioning boundary, and private-key non-custody.
- Manual gate evidence verifier, reviewer signoff fields, and blocker
  rejection behavior.
- Public-testnet exit evidence schema, independent-operator requirement,
  scenario proof requirements, incident closure, and final report approval.
- External security-review evidence schema, signed scope, topic closure,
  findings status, remediation evidence, accepted risks, and auditor closure.
- Legal/compliance evidence schema, launch allocation boundary, distribution
  basis, prohibited use cases, disclosures, and final legal/compliance decision.
- Wallet custody evidence schema, recovery standard, address versioning,
  backup rotation, private-key handling, custody posture, and final approval.
- Production deployment evidence schema, source freeze, release archive,
  deployment hardening, monitoring, backup/restore, rollback, incident response,
  and post-deploy audit approval.
- Mainnet decision evidence schema, release manifest binding, checksum
  verification, approved allocation binding, manual gate aggregation, and final
  launch authorization.
- Daemon exposure risks, authentication, authorization, CORS, rate limits, and
  deployment hardening.

## Required Outputs

- Reviewed source hash.
- Findings by severity.
- Reproduction steps for each finding.
- Remediation commit or explicit accepted risk.
- Final auditor closure statement.
- Completed `tools\spacecash_security_review_evidence.py --require-complete`
  result.
- Completed wallet custody evidence verifier result for the wallet/custody
  boundary.
- Completed production deployment evidence verifier result for the deployment
  runbook boundary.
- Completed mainnet decision verifier result for the final launch boundary.

## Review Packet Command

Prepare the packet for an external reviewer with:

```powershell
tools\nsp_python.cmd tools\spacecash_security_review_packet.py --out-dir _tmp\spacecash_security_review_packet --force
tools\nsp_python.cmd tools\spacecash_security_review_evidence.py --template-out _tmp\spacecash_security_review_evidence_template.json
tools\nsp_python.cmd tools\spacecash_security_review_evidence.py --verify _tmp\spacecash_security_review_evidence_template.json
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --template-out _tmp\spacecash_legal_compliance_evidence_template.json
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --verify _tmp\spacecash_legal_compliance_evidence_template.json
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --template-out _tmp\spacecash_wallet_custody_evidence_template.json
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --verify _tmp\spacecash_wallet_custody_evidence_template.json
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --template-out _tmp\spacecash_production_deployment_evidence_template.json
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --verify _tmp\spacecash_production_deployment_evidence_template.json
tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --template-out _tmp\spacecash_mainnet_decision_template.json
tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --verify _tmp\spacecash_mainnet_decision_template.json
```

The packet includes the reviewed source manifest, consensus spec JSON, monetary
policy JSON, genesis plan JSON, genesis allocation template/check JSON, manual
gate evidence template/check JSON, public-testnet evidence template/check JSON,
security-review evidence template/check JSON, legal/compliance evidence
template/check JSON, wallet custody evidence template/check JSON, production
deployment evidence template/check JSON, mainnet decision template/check JSON,
wallet policy JSON, copied security docs, attack surface notes, a review matrix,
per-topic reviewer workpapers under `audit/topics/`, a signed-scope template,
a finding template, an auditor closure template, a path-connected
`security_review_evidence_workbench.json`, an empty findings log, a remediation
tracker, and `SHA256SUMS.txt`. This packet is
preparation only; it does not complete the external security review gate without
auditor findings, remediation evidence, accepted-risk documentation, and final
closure that passes `tools\nsp_python.cmd tools\spacecash_security_review_evidence.py --require-complete`.
It also does not complete the legal/compliance gate without a completed
`tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --require-complete` review, or the
wallet custody gate without `tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --require-complete`,
or the deployment gate without
`tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --require-complete`, or the
final launch boundary without
`tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --require-complete`.

## Out Of Scope Until Defined

- Exchange listing.
- Securities analysis.
- Tax advice.
- Custodial wallet operation.
- Public mainnet validator economics.

# SpaceCash Mainnet Gate

Current final decision handoff packet: `MAINNET_DECISION_REVIEWER_HANDOFF_2026-06-10.md`.

SpaceCash cannot be called mainnet until every required gate below is complete
and reviewed. This is an engineering gate, not legal approval.

## Current Status

- Mode: local signed devnet.
- Ledger: SQLite-backed local state.
- Wallets: signed browser wallets with encrypted local backup.
- Monetary policy: `tools\nsp_python.cmd tools\spacecash_monetary_policy.py` publishes the
  current supply, issuance, fee, and treasury boundary and deterministic policy
  hash for review.
- Genesis plan: `tools\nsp_python.cmd tools\spacecash_genesis_plan.py` publishes the current
  devnet-to-mainnet allocation boundary and deterministic plan hash for review.
- Genesis allocation verifier: `tools\nsp_python.cmd tools\spacecash_genesis_allocation.py`
  writes a schema-bound allocation template and verifies allocation hashes,
  duplicate addresses, exact supply totals, and approval fields.
- Wallet policy: `tools\nsp_python.cmd tools\spacecash_wallet_policy.py` publishes the
  current recovery/custody boundary and deterministic policy hash for review.
- Blocks: deterministic local block batches with producer identity.
- Proofs: transaction inclusion proofs verify txids against block Merkle roots.
- Sync: verified append-only peer snapshot import only.
- Consensus: local producer allowlist plus signed checkpoint quorum evidence.
- Consensus spec: `tools\nsp_python.cmd tools\spacecash_consensus_spec.py` publishes a
  versioned devnet consensus envelope and deterministic spec hash for review.
- Testing: core and daemon/product regression coverage exists; broader wallet
  UI, import rollback, deployment, and adversarial network coverage is still
  pending.
- Readiness reporting: `tools\nsp_python.cmd tools\spacecash_cli.py readiness` and
  `GET /readiness` expose automated blockers separately from manual launch
  blockers.
- Candidate ledger: `tools\nsp_python.cmd tools\spacecash_candidate.py` can build a fresh
  signed-only DB where automated readiness gates pass without mutating the
  historical devnet database.
- Public-testnet package: `tools\nsp_python.cmd tools\spacecash_testnet_plan.py` can build
  a multi-validator candidate package with node configs, checklist, report
  templates, evidence template, and checksums.
- Local testnet rehearsal: `tools\nsp_python.cmd tools\spacecash_testnet_rehearsal.py` can
  start temporary package nodes and archive health, readiness, manifest, audit,
  checkpoint, peer, gossip, and sync-preview evidence.
- Security-review packet: `tools\nsp_python.cmd tools\spacecash_security_review_packet.py`
  can prepare source hashes, scope docs, attack-surface notes, review matrix,
  findings log, remediation tracker, and checksums for an external auditor.
- Release bundle: `tools\nsp_python.cmd tools\spacecash_release_bundle.py` creates a review
  directory with candidate DB, testnet package, local rehearsal report, release
  manifest, consensus spec, monetary policy, genesis plan, genesis allocation
  template/check, wallet custody evidence template/check, production deployment
  evidence template/check, mainnet decision template/check, wallet policy,
  security-review packet, summaries, README, and SHA256 checksums.
- Manual-gate docs: testnet, security audit, wallet custody, deployment, legal,
  and reviewer evidence requirements are now tracked in `docs/spacecash`.
- Blocker elimination plan: `docs/spacecash/BLOCKER_ELIMINATION_PLAN.md` and
  `tools\nsp_python.cmd tools\spacecash_gate_evidence.py` define the executable evidence
  path for the five remaining human signoff blockers.
- Manual gate workbench: `tools\nsp_python.cmd tools\spacecash_manual_gate_workbench.py`
  prepares a consolidated manual-gate packet with per-gate workpapers, a
  completion matrix, evidence binder, composite evidence template/check, and
  checksums without approving any gate.
- Public-testnet evidence: `tools\nsp_python.cmd tools\spacecash_public_testnet_evidence.py`
  defines the node/operator/scenario/incident/final-report evidence required
  before `public_testnet_complete` can be accepted.
- Security-review evidence: `tools\nsp_python.cmd tools\spacecash_security_review_evidence.py`
  defines the signed-scope, topic-review, findings, remediation, accepted-risk,
  and auditor-closure evidence required before
  `external_security_review_complete` can be accepted.
- Legal/compliance evidence: `tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py`
  defines the use-case, distribution, disclosure, jurisdiction, tax/payment,
  restricted-product, operational-control, and final-decision evidence required
  before `legal_compliance_review_complete` can be accepted.
- Wallet custody evidence: `tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py`
  defines the recovery standard, address versioning, backup rotation,
  lost-key/compromised-key, private-key handling, custody posture, and final
  approval evidence required before
  `wallet_recovery_custody_policy_complete` can be accepted.
- Production deployment evidence: `tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py`
  defines source freeze, release archive, deployment hardening, monitoring,
  backup/restore, rollback, incident response, and post-deploy audit evidence
  required before `production_deployment_runbook_complete` can be accepted.
- Mainnet decision evidence: `tools\nsp_python.cmd tools\spacecash_mainnet_decision.py`
  aggregates the release manifest, release-bundle checksums, security-review
  packet checksums, approved genesis allocation, manual gate evidence, all
  gate-specific evidence files, and final launch authorization before any
  mainnet claim can be accepted. Its workbench command prepares artifact,
  gate, checksum, source-freeze, and final-authorization review sheets without
  approving launch.

## Required Gates

1. Consensus specification
   - Public written consensus rules. Current devnet spec is in
     `CONSENSUS_SPEC.md`; public-mainnet consensus remains pending.
   - Validator lifecycle rules.
   - Fork choice and reorg policy.
   - Finality/checkpoint semantics.

2. Network readiness
   - Public testnet.
   - Multiple independently operated nodes.
   - Bootstrap peer list.
   - Peer identity policy.
   - Rate limiting and abuse handling.
   - See `PUBLIC_TESTNET_RUNBOOK.md`.

3. Wallet readiness
   - Recovery phrase standard.
   - Address versioning.
   - Encrypted backup rotation policy.
   - Lost-key and compromised-key guidance.
   - Hardware wallet or custody plan.
   - See `WALLET_RECOVERY_CUSTODY_POLICY.md`.

4. Ledger readiness
   - No unsigned spend compatibility on mainnet.
   - Migration plan from devnet to launch allocation.
   - Genesis allocation review with `--require-approved` verifier output.
   - Supply, treasury, fee, burn, and distribution policy.
   - Replay protection across testnet/mainnet.

5. Security readiness
   - Full automated test suite.
   - Threat model review.
   - Dependency inventory.
   - External audit.
   - Reproducible release manifest.
   - Incident response and rollback plan.
   - See `SECURITY_AUDIT_SCOPE.md`.

6. Product/payment readiness
   - Legal/compliance review.
   - Tax handling.
   - Refund and fulfillment policy.
   - Restricted-product controls.
   - Customer support workflow.
   - See `LEGAL_COMPLIANCE_GATE.md`.

7. Deployment readiness
   - Production runbook.
   - Monitored rollout.
   - Backup and rollback procedure.
   - Archived release bundle.
   - See `PRODUCTION_DEPLOYMENT_RUNBOOK.md`.

## Release Candidate Command Set

Run these commands before any candidate build:

```powershell
tools\nsp_python.cmd -m py_compile app.py spacecash_core\protocol.py spacecash_core\ledger.py tools\spacecash_cli.py tools\spacecash_candidate.py tools\spacecash_consensus_spec.py tools\spacecash_daemon.py tools\spacecash_gate_evidence.py tools\spacecash_genesis_allocation.py tools\spacecash_genesis_plan.py tools\spacecash_legal_compliance_evidence.py tools\spacecash_mainnet_decision.py tools\spacecash_monetary_policy.py tools\spacecash_production_deployment_evidence.py tools\spacecash_public_testnet_evidence.py tools\spacecash_release_bundle.py tools\spacecash_smoke.py tools\spacecash_security_review_evidence.py tools\spacecash_security_review_packet.py tools\spacecash_testnet_plan.py tools\spacecash_testnet_rehearsal.py tools\spacecash_release_manifest.py tools\spacecash_wallet_custody_evidence.py tools\spacecash_wallet_policy.py
tools\nsp_python.cmd -m unittest discover -s tests -v
tools\nsp_python.cmd tools\spacecash_smoke.py
tools\nsp_python.cmd tools\spacecash_consensus_spec.py --out _tmp\spacecash_consensus_spec.json
tools\nsp_python.cmd tools\spacecash_monetary_policy.py --out _tmp\spacecash_monetary_policy.json
tools\nsp_python.cmd tools\spacecash_genesis_plan.py --out _tmp\spacecash_genesis_plan.json
tools\nsp_python.cmd tools\spacecash_genesis_allocation.py --template-out _tmp\spacecash_genesis_allocation_template.json
tools\nsp_python.cmd tools\spacecash_genesis_allocation.py --verify _tmp\spacecash_genesis_allocation_template.json
tools\nsp_python.cmd tools\spacecash_gate_evidence.py --template-out _tmp\spacecash_manual_gate_evidence_template.json
tools\nsp_python.cmd tools\spacecash_gate_evidence.py --verify _tmp\spacecash_manual_gate_evidence_template.json
tools\nsp_python.cmd tools\spacecash_manual_gate_workbench.py --workbench-out-dir _tmp\spacecash_manual_gate_workbench --force
tools\nsp_python.cmd tools\spacecash_public_testnet_evidence.py --template-out _tmp\spacecash_public_testnet_evidence_template.json
tools\nsp_python.cmd tools\spacecash_public_testnet_evidence.py --verify _tmp\spacecash_public_testnet_evidence_template.json
tools\nsp_python.cmd tools\spacecash_security_review_evidence.py --template-out _tmp\spacecash_security_review_evidence_template.json
tools\nsp_python.cmd tools\spacecash_security_review_evidence.py --verify _tmp\spacecash_security_review_evidence_template.json
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --template-out _tmp\spacecash_legal_compliance_evidence_template.json
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --verify _tmp\spacecash_legal_compliance_evidence_template.json
tools\nsp_python.cmd tools\spacecash_legal_compliance_evidence.py --workbench-out-dir _tmp\spacecash_legal_compliance_workbench --force
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --template-out _tmp\spacecash_wallet_custody_evidence_template.json
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --verify _tmp\spacecash_wallet_custody_evidence_template.json
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --workbench-out-dir _tmp\spacecash_wallet_custody_workbench --force
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --template-out _tmp\spacecash_production_deployment_evidence_template.json
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --verify _tmp\spacecash_production_deployment_evidence_template.json
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --workbench-out-dir _tmp\spacecash_production_deployment_workbench --force
tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --template-out _tmp\spacecash_mainnet_decision_template.json
tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --verify _tmp\spacecash_mainnet_decision_template.json
tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --workbench-out-dir _tmp\spacecash_mainnet_decision_workbench --force
tools\nsp_python.cmd tools\spacecash_wallet_policy.py --out _tmp\spacecash_wallet_policy.json
tools\nsp_python.cmd tools\spacecash_candidate.py --db _tmp\spacecash_candidate.sqlite3 --validators 3 --quorum 2 --force
tools\nsp_python.cmd tools\spacecash_testnet_plan.py --out-dir _tmp\spacecash_testnet_plan --force
tools\nsp_python.cmd tools\spacecash_testnet_rehearsal.py --out-dir _tmp\spacecash_testnet_rehearsal --force
tools\nsp_python.cmd tools\spacecash_security_review_packet.py --out-dir _tmp\spacecash_security_review_packet --force
tools\nsp_python.cmd tools\spacecash_cli.py audit
tools\nsp_python.cmd tools\spacecash_cli.py readiness
tools\nsp_python.cmd tools\spacecash_release_manifest.py --check-compile --check-consensus-spec --check-monetary-policy --check-genesis-plan --check-genesis-allocation --check-manual-gate-evidence --check-public-testnet-evidence --check-security-review-evidence --check-legal-compliance-evidence --check-wallet-custody-evidence --check-production-deployment-evidence --check-mainnet-decision --check-wallet-policy --run-units --audit-live --include-readiness --run-smoke --run-candidate --run-testnet-plan --run-testnet-rehearsal --run-security-packet --out _tmp\spacecash_release_manifest.json
tools\nsp_python.cmd tools\spacecash_release_bundle.py --out-dir _tmp\spacecash_release_bundle --force
```

The release candidate fails if any command fails, if the live audit is invalid,
if readiness shows unresolved automated blockers on the candidate ledger, or if
the manifest source hash is not tied to a reviewed bundle artifact.

The security-review packet is not an audit result. The external review gate
remains blocked until an auditor reviews the packet source hash, records
findings, verifies remediation, and signs closure.

## Mainnet Decision Rule

Mainnet remains blocked until:

- All required gates are complete.
- `MANUAL_GATES.md` has reviewer evidence for every manual gate.
- The completed manual gate evidence file passes `tools\spacecash_gate_evidence.py --require-complete`.
- Public-testnet exit evidence passes `tools\spacecash_public_testnet_evidence.py --require-complete`.
- External security-review evidence passes `tools\spacecash_security_review_evidence.py --require-complete`.
- Legal/compliance evidence passes `tools\spacecash_legal_compliance_evidence.py --require-complete`.
- Wallet recovery/custody evidence passes `tools\spacecash_wallet_custody_evidence.py --require-complete`.
- Production deployment evidence passes `tools\spacecash_production_deployment_evidence.py --require-complete`.
- Final mainnet decision evidence passes `tools\spacecash_mainnet_decision.py --require-complete`.
- The threat model has no unresolved launch blockers.
- The release manifest is archived.
- External review is complete.
- Legal/compliance review clears the intended use.

Until then, all UI, API, and documentation should continue to call SpaceCash a
local signed devnet.

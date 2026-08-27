# SpaceCash Threat Model

SpaceCash is still a local signed devnet. This document names the current
security assumptions and mainnet blockers so engineering work does not drift
into launch claims before the system is ready.

## Assets

- Wallet private keys in browser storage and encrypted wallet backup JSON.
- Monetary policy hash and tokenomics review artifacts.
- Genesis plan hash and launch allocation review artifacts.
- Genesis allocation template, allocation hash, and verifier output.
- Manual gate evidence, reviewer signoff fields, and blocker status.
- Public-testnet exit evidence, independent-operator reports, scenario proof,
  incident closure, and final report approval.
- External security-review evidence, signed scope, findings status,
  remediation evidence, accepted risks, and auditor closure.
- Legal/compliance evidence, approved use case, prohibited uses,
  jurisdictional availability, disclosures, operating controls, and final
  launch decision.
- Wallet recovery/custody policy hash, custody evidence, recovery decisions,
  private-key handling approval, and release artifacts.
- Production deployment evidence, release archives, rollback plans, monitoring
  plans, backup/restore rehearsal, incident response plans, and post-deploy
  audit records.
- Mainnet decision evidence, reviewed source hash, release checksum manifests,
  approved allocation pointer, gate evidence pointers, and launch authorization.
- Ledger integrity in `spacecash_devnet.sqlite3`.
- Total supply invariant and treasury balance.
- Signed transaction payloads, nonces, and mempool state.
- Block hashes, producer ids, producer seals, snapshots, and chain manifests.
- Peer registry, bootstrap peer configuration, and sync import history.
- Versioned consensus specification and spec hash.
- Product redemption receipts and fulfillment status.
- Release manifests, review packets, findings logs, and remediation evidence.

## Trust Boundaries

- Browser wallet: owns private keys and creates signatures. The server should
  never need private keys.
- Flask site: user-facing wallet and checkout surface. It is not the consensus
  boundary.
- SpaceCash daemon: standalone ledger API and node surface.
- SQLite ledger: current source of truth for local devnet state.
- Peer HTTP APIs: untrusted until manifest, snapshot, signature, policy, and
  append-only checks pass.
- Product catalog: trusted only for product metadata and eligibility, not for
  ledger integrity.

## Current Controls

- Signed P-256 wallet spends bound to `chain_id`, payload version, action,
  amount, sender, and nonce.
- Per-address nonce table for settled signed spends.
- Signed mempool queue with balance reservation before settlement.
- Deterministic block batches with block version, ordered txids, producer id,
  and producer seal.
- Transaction inclusion proofs can verify a txid against the block Merkle root
  without trusting the explorer response body.
- Audit recomputes block linkage, balances, total supply, signed spend
  integrity, mempool validity, and checkpoint vote validity.
- Snapshots digest blocks, transactions, and wallet public keys together.
- Sync import accepts only verified append-only peer-ahead snapshots and writes
  a SQLite backup before import.
- Producer allowlist rejects new versioned blocks from unknown producers.
- Bootstrap peers and peer gossip are explicit local configuration.
- Checkpoint votes must be signed by locally registered validator wallets.
- `tools/spacecash_consensus_spec.py` publishes the current devnet consensus
  envelope and deterministic spec hash for review.
- `tools/spacecash_monetary_policy.py` publishes the current fixed-supply,
  treasury/faucet, fee, and tokenomics boundary with a deterministic policy hash
  for review.
- `tools/spacecash_genesis_plan.py` publishes the current devnet-to-mainnet
  genesis/allocation boundary with a deterministic plan hash for review.
- `tools/spacecash_genesis_allocation.py` writes and verifies the allocation
  schema, allocation hash, duplicate-address rules, supply total, and approval
  fields for any future launch allocation.
- `tools/spacecash_gate_evidence.py` writes and verifies the evidence template
  for the five manual mainnet gates, including reviewer fields and
  `--require-complete` rejection.
- `tools/spacecash_public_testnet_evidence.py` writes and verifies public
  testnet exit evidence for independent nodes, required scenarios, incidents,
  and final report approval.
- `tools/spacecash_security_review_evidence.py` writes and verifies external
  security-review closure evidence for signed scope, topic coverage, findings,
  remediation, accepted risks, auditor approval, and the manual audit gate.
- `tools/spacecash_legal_compliance_evidence.py` writes and verifies
  legal/compliance review evidence for use-case approval, distribution basis,
  disclosures, operational controls, jurisdictional availability, and final
  launch decision.
- `tools/spacecash_wallet_custody_evidence.py` writes and verifies wallet
  recovery/custody evidence for recovery standard, address versioning, backup
  rotation, lost-key and compromised-key procedures, private-key handling,
  custody posture, and final approval.
- `tools/spacecash_production_deployment_evidence.py` writes and verifies
  production deployment evidence for source freeze, release archive, HTTP
  hardening, monitoring, backup/restore, rollback, incident response, and
  post-deploy audit approval.
- `tools/spacecash_mainnet_decision.py` writes and verifies the final mainnet
  decision evidence that binds release manifest, checksum manifests, approved
  genesis allocation, manual gate evidence, gate-specific evidence, and launch
  authorization.
- `tools/spacecash_wallet_policy.py` publishes the current wallet
  recovery/custody boundary and deterministic policy hash for review.
- Browser wallet backups use a versioned encrypted envelope with
  PBKDF2-SHA256-250000 and AES-256-GCM.
- `tests/test_spacecash_core.py` covers core protocol metadata, signed mempool
  nonce behavior, checkpoint votes, append-only sync import, and producer-policy
  rejection.
- `tests/test_spacecash_daemon.py` covers daemon health/config/status/audit
  routes, signed product-payment settlement, receipt lookup, and mined nonce
  rejection over HTTP.
- `tools/spacecash_smoke.py` covers a temporary-ledger signed wallet, mempool,
  block, checkpoint, snapshot, peer gossip, and audit path.
- `tools/spacecash_release_manifest.py` hashes critical source files and can run
  compile, unit, smoke, live audit, and readiness-report checks.
- `SpaceCashLedger.mainnet_readiness()`, `tools/spacecash_cli.py readiness`,
  and daemon `GET /readiness` expose automated and manual launch blockers.
- `tools/spacecash_candidate.py` builds a clean signed-only candidate ledger for
  automated-gate testing without rewriting historical devnet state.
- `tools/spacecash_release_bundle.py` creates a reviewable artifact directory
  with candidate DB, public-testnet package, manifest, summaries, README, and
  SHA256 checksums.
- `tools/spacecash_testnet_plan.py` creates a multi-validator public-testnet
  package with node configs and evidence templates for reviewer signoff.
- `tools/spacecash_testnet_rehearsal.py` starts temporary local package nodes
  and archives route, peer, checkpoint, and sync-preview evidence before a
  public testnet is attempted.
- `tools/spacecash_security_review_packet.py` prepares an external-review
  packet with source hashes, audit scope, attack-surface notes, review matrix,
  findings log, remediation tracker, and checksums.
- Manual-gate documents define required evidence for public testnet, external
  security review, wallet custody, deployment, and legal/compliance review.

## Known Open Risks

- A versioned devnet consensus spec exists, but public mainnet consensus is not
  implemented. Current fork choice is append-only and intentionally does not
  perform automatic reorgs.
- Validator voting is local checkpoint evidence, not a full consensus protocol.
- The live DB still has legacy unsigned spend compatibility warnings from early
  devnet history.
- Readiness reporting can identify launch blockers, but it cannot replace
  external audit, public testnet operations, or legal/compliance review.
- Candidate ledgers are test artifacts. They do not define a reviewed launch
  allocation, custody process, or production validator set.
- Monetary policy artifacts document current devnet behavior; they do not
  approve public distribution, treasury governance, fees, or market disclosures.
- Genesis plan artifacts document the launch boundary; they do not approve an
  allocation file or migration.
- Genesis allocation verifier output can reject malformed allocation files, but
  it does not replace distribution, treasury, or legal/compliance approval.
- Release bundles are local review artifacts until their manifest source hash,
  candidate DB, and checksums are archived and reviewed.
- Security-review packets are reviewer inputs, not proof that an external audit
  has happened or closed.
- Wallet policy artifacts are reviewer inputs, not approval for production
  custody or recovery operations.
- Wallet custody evidence verification can reject incomplete recovery/custody
  approval records, but it does not replace the actual policy, UX, legal,
  support, or operational work.
- Production deployment evidence verification can reject incomplete runbook
  records, but it does not replace real deployment rehearsals, monitoring,
  backup restoration, rollback ownership, or incident response execution.
- Mainnet decision evidence verification can reject incomplete launch packets,
  but it does not replace actual review, signoff, legal/compliance judgment,
  public testnet execution, external audit closure, or deployment execution.
- Manual-gate documents are checklists; they are not themselves proof that the
  gate is complete.
- Manual gate evidence verification can prove a completed file is structured,
  but it cannot replace actual public testnet operations, auditor closure, or
  legal/compliance judgment.
- Public testnet evidence verification can reject incomplete exit evidence, but
  it does not prove the testnet happened until real independently operated node
  reports are attached and reviewed.
- Security review evidence verification can reject incomplete audit closure, but
  it does not replace the auditor's actual testing, findings, remediation
  review, or professional judgment.
- Legal/compliance evidence verification can reject incomplete review records,
  but it does not replace legal advice, tax advice, regulatory analysis, or
  counsel judgment.
- Browser private keys can be lost or stolen if the browser profile is lost,
  compromised, or backed up insecurely.
- Encrypted backup strength depends on user passphrase quality.
- There is no recovery phrase standard yet.
- There is no completed hardware wallet support or approved custody operations
  policy.
- There is no external audit, public testnet, exchange listing process, tax
  treatment, securities analysis, or payment compliance review.
- Peer gossip can discover URLs, but it does not yet provide authenticated peer
  identity, rate limiting, ban scoring, or network-wide topology health.
- Daemon APIs are local development HTTP endpoints and are not hardened for
  exposure to the public internet.
- Product fulfillment still requires operational controls outside the ledger.

## Mainnet Blockers

1. Specify consensus beyond append-only local import.
2. Define validator enrollment, rotation, quorum, slashing/removal, and reorg
   policy.
3. Create a public testnet with reproducible node setup and monitored bootstrap
   peers.
4. Remove or permanently quarantine legacy unsigned spend compatibility.
5. Approve a fresh mainnet genesis allocation file and distribution basis after
   it passes `tools\spacecash_genesis_allocation.py --require-approved`.
6. Complete wallet recovery/custody evidence for recovery phrase, address
   versioning, backup rotation, private-key handling, and custody policy.
7. Add authentication, authorization, rate limiting, CORS policy, and deployment
   hardening for daemon APIs.
8. Expand automated tests for wallet UI flows, additional daemon routes, import
   rollback, and deployment behavior.
9. Complete external security review evidence with signed scope, findings,
   remediation, accepted risks, and auditor closure.
10. Complete legal/compliance evidence for use case, distribution, disclosures,
   jurisdictional availability, treasury controls, and final decision.
11. Complete production deployment evidence for release manifests, tagged
   builds, reproducible deployment steps, monitoring, backup/restore, incident
   response, and rollback procedures.
12. Complete final mainnet decision evidence binding every approved gate,
   checksum manifest, release manifest, allocation file, and launch
   authorization.
13. Complete public distribution, treasury governance, fee/burn, and tokenomics
   review.
14. Complete legal, compliance, tax, and product-payment review before any
   real-money use.

## Review Cadence

Update this document whenever a new external interface, wallet behavior,
consensus rule, sync rule, or product-payment path is added. A mainnet release
candidate should not proceed while any blocker above is unresolved.

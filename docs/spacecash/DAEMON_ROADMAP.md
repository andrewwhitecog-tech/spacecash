# SpaceCash Daemon Roadmap

SpaceCash is currently a signed local devnet embedded in NorthStar Prime. The
first extraction step is now present as `spacecash_core`,
`tools/spacecash_cli.py`, and a local HTTP daemon in
`tools/spacecash_daemon.py`.

## Current Independent Surface

- `spacecash_core.protocol`: chain constants, canonical JSON, address derivation,
  wallet export metadata, amount conversion, payload hashes, block hashes,
  deterministic consensus spec/hash, monetary policy/hash, genesis plan/hash,
  wallet policy/hash, fork-choice policy, and producer policy defaults.
- `spacecash_core.ledger.SpaceCashLedger`: SQLite schema migration, status,
  audit, machine-readable mainnet readiness gates, block/transaction lookup,
  Merkle transaction inclusion proofs, signed mempool queueing/mining, product
  receipt records, node identity, chain manifests/snapshots with wallet public
  keys, peer registry, bootstrap peer configuration, producer allowlist policy,
  peer gossip discovery, signed checkpoint vote policy and quorum evaluation,
  explicit append-only fork-choice evaluation, non-mutating sync candidate
  previews, and guarded append-only imports with backups.
- `tools/spacecash_cli.py`: standalone config/status/audit/block/tx/sync
  inspection.
- `tools/spacecash_consensus_spec.py`: deterministic consensus specification
  writer with a stable spec hash for auditors, release bundles, and operators.
- `tools/spacecash_monetary_policy.py`: deterministic supply, issuance, fee,
  and treasury policy writer with a stable policy hash for auditors, release
  bundles, and operators.
- `tools/spacecash_genesis_plan.py`: deterministic devnet-to-mainnet genesis
  and allocation boundary writer with a stable plan hash for auditors, release
  bundles, and operators.
- `tools/spacecash_genesis_allocation.py`: deterministic allocation template
  writer and verifier for allocation hash, required fields, duplicate addresses,
  supply totals, and approval gate status.
- `tools/spacecash_gate_evidence.py`: manual mainnet-gate evidence template and
  verifier for public testnet, external audit, legal/compliance, wallet custody,
  and production deployment signoff.
- `tools/spacecash_public_testnet_evidence.py`: public-testnet exit evidence
  template and verifier for independent node operators, required scenario
  proofs, incident closure, and final report approval.
- `tools/spacecash_security_review_evidence.py`: external security-review
  closure evidence template and verifier for signed scope, topic coverage,
  findings, remediation, accepted risks, and auditor signoff.
- `tools/spacecash_legal_compliance_evidence.py`: legal/compliance review
  evidence template and verifier for approved use case, distribution basis,
  disclosures, operating controls, jurisdictions, and final decision.
- `tools/spacecash_wallet_custody_evidence.py`: wallet recovery/custody
  evidence template and verifier for recovery standard, address versioning,
  backup rotation, lost-key and compromised-key procedures, custody posture,
  private-key handling, and final approval.
- `tools/spacecash_production_deployment_evidence.py`: production deployment
  evidence template and verifier for source freeze, release archive, HTTP
  hardening, monitoring, backup/restore, rollback, incident response, and
  post-deploy audit approval.
- `tools/spacecash_mainnet_decision.py`: final decision template and verifier
  that aggregates release manifest, release-bundle checksums, security-review
  packet checksums, approved genesis allocation, manual gate evidence, all
  gate-specific evidence files, and launch authorization.
- `tools/spacecash_wallet_policy.py`: deterministic wallet recovery/custody
  policy writer with a stable policy hash for auditors, release bundles, and
  operators.
- `tools/spacecash_smoke.py`: temporary-ledger smoke checks for signed wallets,
  mempool mining, checkpoint quorum, snapshots, peer gossip, and audit.
- `tools/spacecash_candidate.py`: reproducible signed-only candidate ledger
  builder that proves automated readiness gates can pass on a clean DB without
  rewriting historical devnet state.
- `tools/spacecash_release_bundle.py`: review artifact builder that writes the
  clean candidate DB, release manifest, candidate summary, bundle summary,
  README, public-testnet package, local rehearsal report, security-review
  packet, genesis allocation template/check, copied manual-gate docs, and
  SHA256 checksums into one directory.
- `tools/spacecash_testnet_plan.py`: public-testnet package builder with a
  multi-validator candidate DB, node configs, operator checklist, report
  templates, manual-gate evidence template, and checksums.
- `tools/spacecash_testnet_rehearsal.py`: local multi-node rehearsal runner
  that starts temporary nodes, checks health/readiness/manifests/audits,
  checkpoint quorum, bootstrap peers, gossip, sync previews, and writes a
  rehearsal evidence report.
- `tools/spacecash_security_review_packet.py`: external-review packet builder
  with source manifest, copied security docs, attack-surface notes, review
  matrix, findings log, remediation tracker, and SHA256 checksums.
- `tests/test_spacecash_core.py`: standard-library regression tests for protocol
  metadata, signed mempool nonce behavior, checkpoint votes, append-only sync
  import, and producer-policy rejection.
- `tests/test_spacecash_daemon.py`: HTTP daemon regression tests for health,
  config, status, audit, signed product-payment settlement, receipt lookup, and
  mined nonce rejection.
- `tools/spacecash_release_manifest.py`: deterministic release manifest with
  critical source hashes, protocol metadata, and optional compile, spec,
  policy, manual-gate evidence, public-testnet evidence, security-review
  evidence, legal/compliance evidence, wallet-custody evidence,
  production-deployment evidence, unit, smoke, testnet, security-packet, and
  audit checks.
- `docs/spacecash/CONSENSUS_SPEC.md`, `MONETARY_POLICY.md`,
  `GENESIS_PLAN.md`, `THREAT_MODEL.md`, and `MAINNET_GATE.md`: launch-risk
  tracking, consensus, monetary, and allocation boundaries, mainnet blockers,
  and release candidate gates.
- `docs/spacecash/MANUAL_GATES.md` plus the testnet, audit, wallet custody,
  deployment, and legal/compliance docs: human-review evidence requirements for
  the remaining non-code gates.
- `northstar_catalog`: shared product lookup and SpaceCash eligibility checks
  for Prime and Chromatic catalog sources.
- `tools/spacecash_daemon.py`: HTTP daemon outside Flask for status, audit,
  wallet registration, faucet, transfers, generic redemptions, and catalog-backed
  product payments.

Example:

```powershell
python tools/spacecash_cli.py status
python tools/spacecash_cli.py consensus-spec
python tools/spacecash_cli.py monetary-policy
python tools/spacecash_cli.py genesis-plan
python tools/spacecash_cli.py genesis-allocation
python tools/spacecash_cli.py security-review-evidence
python tools/spacecash_cli.py legal-compliance-evidence
python tools/spacecash_cli.py wallet-custody-evidence
python tools/spacecash_cli.py production-deployment-evidence
python tools/spacecash_cli.py mainnet-decision
python tools/spacecash_cli.py node
python tools/spacecash_cli.py policy
python tools/spacecash_cli.py wallet-policy
python tools/spacecash_cli.py producers
python tools/spacecash_cli.py validators
python tools/spacecash_cli.py checkpoint-quorum
python tools/spacecash_cli.py bootstrap-peers
python tools/spacecash_cli.py chain-manifest
python tools/spacecash_cli.py chain-snapshot
python tools/spacecash_cli.py audit
python tools/spacecash_cli.py readiness
python tools/spacecash_cli.py blocks --limit 10
python tools/spacecash_cli.py tx-proof SCTX-...
python tools/spacecash_cli.py mempool
python tools/spacecash_cli.py mempool-mine --limit 10
python tools/spacecash_cli.py peers
python tools/spacecash_cli.py peer-add http://127.0.0.1:8876 --label local
python tools/spacecash_cli.py peer-check http://127.0.0.1:8876 --snapshot
python tools/spacecash_cli.py peer-fork-choice http://127.0.0.1:8876
python tools/spacecash_cli.py peer-sync-preview http://127.0.0.1:8876
python tools/spacecash_cli.py peer-sync-import http://127.0.0.1:8876 --yes
python tools/spacecash_cli.py sync-candidates
python tools/spacecash_cli.py sync-imports
python tools/spacecash_cli.py peers-check
python tools/spacecash_cli.py peer-gossip --check
python tools/spacecash_cli.py checkpoint-votes
python tools/spacecash_cli.py orders
python tools/spacecash_cli.py orders-backfill --actor operator
python tools/spacecash_cli.py order-update SCOR-... --status approved
python -m unittest discover -s tests -v
python tools/spacecash_smoke.py
python tools/spacecash_consensus_spec.py --out _tmp\spacecash_consensus_spec.json
python tools/spacecash_monetary_policy.py --out _tmp\spacecash_monetary_policy.json
python tools/spacecash_genesis_plan.py --out _tmp\spacecash_genesis_plan.json
python tools/spacecash_genesis_allocation.py --template-out _tmp\spacecash_genesis_allocation_template.json
python tools/spacecash_genesis_allocation.py --verify _tmp\spacecash_genesis_allocation_template.json
python tools/spacecash_gate_evidence.py --template-out _tmp\spacecash_manual_gate_evidence_template.json
python tools/spacecash_gate_evidence.py --verify _tmp\spacecash_manual_gate_evidence_template.json
python tools/spacecash_public_testnet_evidence.py --template-out _tmp\spacecash_public_testnet_evidence_template.json
python tools/spacecash_public_testnet_evidence.py --verify _tmp\spacecash_public_testnet_evidence_template.json
python tools/spacecash_security_review_evidence.py --template-out _tmp\spacecash_security_review_evidence_template.json
python tools/spacecash_security_review_evidence.py --verify _tmp\spacecash_security_review_evidence_template.json
python tools/spacecash_legal_compliance_evidence.py --template-out _tmp\spacecash_legal_compliance_evidence_template.json
python tools/spacecash_legal_compliance_evidence.py --verify _tmp\spacecash_legal_compliance_evidence_template.json
python tools/spacecash_wallet_custody_evidence.py --template-out _tmp\spacecash_wallet_custody_evidence_template.json
python tools/spacecash_wallet_custody_evidence.py --verify _tmp\spacecash_wallet_custody_evidence_template.json
python tools/spacecash_production_deployment_evidence.py --template-out _tmp\spacecash_production_deployment_evidence_template.json
python tools/spacecash_production_deployment_evidence.py --verify _tmp\spacecash_production_deployment_evidence_template.json
python tools/spacecash_mainnet_decision.py --template-out _tmp\spacecash_mainnet_decision_template.json
python tools\spacecash_mainnet_decision.py --verify _tmp\spacecash_mainnet_decision_template.json
python tools/spacecash_wallet_policy.py --out _tmp\spacecash_wallet_policy.json
python tools/spacecash_candidate.py --db _tmp\spacecash_candidate.sqlite3 --validators 3 --quorum 2 --force
python tools/spacecash_testnet_plan.py --out-dir _tmp\spacecash_testnet_plan --force
python tools/spacecash_testnet_rehearsal.py --out-dir _tmp\spacecash_testnet_rehearsal --force
python tools/spacecash_security_review_packet.py --out-dir _tmp\spacecash_security_review_packet --force
python tools/spacecash_release_manifest.py --check-compile --check-consensus-spec --check-monetary-policy --check-genesis-plan --check-genesis-allocation --check-manual-gate-evidence --check-public-testnet-evidence --check-security-review-evidence --check-legal-compliance-evidence --check-wallet-custody-evidence --check-production-deployment-evidence --check-mainnet-decision --check-wallet-policy --run-units --audit-live --include-readiness --run-smoke --run-candidate --run-testnet-plan --run-testnet-rehearsal --run-security-packet
python tools/spacecash_release_bundle.py --out-dir _tmp\spacecash_release_bundle --force
python tools/spacecash_daemon.py --port 8876
```

Read-only daemon routes:

- `GET /health`
- `GET /config`
- `GET /consensus/spec`
- `GET /monetary/policy`
- `GET /genesis/plan`
- `GET /genesis/allocation/template`
- `GET /genesis/allocation/check`
- `GET /security/review/evidence/template`
- `GET /security/review/evidence/check`
- `GET /legal/compliance/evidence/template`
- `GET /legal/compliance/evidence/check`
- `GET /wallet/custody/evidence/template`
- `GET /wallet/custody/evidence/check`
- `GET /deployment/evidence/template`
- `GET /deployment/evidence/check`
- `GET /mainnet/decision/template`
- `GET /mainnet/decision/check`
- `GET /wallet/policy`
- `GET /status`
- `GET /node`
- `GET /policy`
- `GET /validators`
- `GET /checkpoint/quorum`
- `GET /checkpoint/votes`
- `GET /chain/manifest`
- `GET /chain/snapshot`
- `GET /audit`
- `GET /readiness`
- `GET /blocks?limit=25`
- `GET /block/<height-or-hash>`
- `GET /tx/<txid>`
- `GET /tx/<txid>/proof`
- `GET /mempool?status=pending`
- `GET /mempool/<pending_id>`
- `GET /peers`
- `GET /bootstrap-peers`
- `GET /sync-candidates?status=peer_ahead_candidate`
- `GET /sync-candidate/<candidate_id>`
- `GET /sync-imports`
- `GET /orders?wallet=<address>&status=pending_review`
- `GET /order/<receipt_id>`
- `GET /order/<receipt_id>/events`

Write daemon routes:

- `GET /wallet/<address>`
- `POST /wallet/new`
- `POST /wallet/register`
- `POST /faucet`
- `POST /transfer`
- `POST /redeem`
- `POST /pay`
- `POST /mempool/transfer`
- `POST /mempool/redeem`
- `POST /mempool/pay`
- `POST /mempool/mine`
- `POST /node/label`
- `POST /policy/producers`
- `POST /policy/producers/add`
- `POST /validators`
- `POST /validators/add`
- `POST /validators/quorum`
- `POST /checkpoint/payload`
- `POST /checkpoint/vote`
- `POST /bootstrap-peers`
- `POST /bootstrap-peers/add`
- `POST /bootstrap-peers/load`
- `POST /chain/verify`
- `POST /chain/fork-choice`
- `POST /peers`
- `POST /peers/record`
- `POST /peers/check`
- `POST /peers/check-all`
- `POST /peers/gossip`
- `POST /peers/fork-choice`
- `POST /peers/sync-preview`
- `POST /peers/sync-preview-all`
- `POST /peers/sync-import`
- `POST /orders/backfill`
- `POST /order/<receipt_id>/status`

Product payment now validates source, product id, price, restricted-product
status, and signed SpaceCash amount through the shared catalog module. Fulfillment
receipt records are created in the daemon as pending review orders. Order review,
contact, and fulfillment status updates are recorded as timestamped events.
Historical product redemptions can be backfilled into receipt records without
changing balances or replaying payments. Tax/shipping rules and final fulfillment
automation are still pending.

The browser wallet now exports encrypted local backups using the versioned
SpaceCash wallet backup envelope, PBKDF2-SHA256-250000, and AES-256-GCM. Plain
legacy backup JSON remains importable for local devnet recovery. A versioned
wallet recovery/custody policy, policy hash, and wallet custody evidence
verifier are implemented for review; production recovery phrase, hardware
wallet, and custody operations still require approval.

The monetary policy is now a hash-pinned review artifact. It documents the
fixed devnet supply cap, treasury/faucet boundary, zero current block reward,
zero current protocol transfer fee, and the manual legal/compliance gate for
public tokenomics, distribution, treasury governance, fees, and market
disclosures.

The genesis plan is now a hash-pinned review artifact. It states that historical
devnet balances do not automatically migrate to mainnet, that candidate private
keys are development artifacts, and that any launch requires a fresh reviewed
allocation file whose total exactly matches the approved supply cap.

The genesis allocation verifier now turns that launch allocation requirement
into a machine-checkable JSON boundary. It rejects duplicate addresses, invalid
amounts, hash mismatches, missing row basis fields, supply mismatches, and
unapproved files in `--require-approved` mode.

The daemon also has a signed mempool surface. `POST /mempool/transfer`,
`/mempool/redeem`, and `/mempool/pay` validate signed payloads, reserve sender
balance against other pending spends, and queue transactions without mutating
settled balances. `POST /mempool/mine` settles queued transactions into
versioned deterministic block batches with a local producer id and producer
seal.

The node boundary now exposes a local node id, node protocol version, chain
manifest, full chain snapshot export, snapshot verifier, and peer registry.
It can fetch peer manifests, classify peers as same/ahead/behind/diverged,
verify downloaded peer snapshots against their advertised digest, record peer
status, and store preview-only sync candidates that classify snapshots as same,
append-only candidates, behind, or diverged. It can also import only verified
append-only peer-ahead snapshots, with a pre-import SQLite backup, transaction
rollback, post-import audit, and automatic restore if audit fails. Fork-choice
evaluation is explicit: higher validated height only wins when the peer extends
the local tip; diverged higher-scoring peers are reported but not reorged.
Bootstrap peer configuration and a local producer allowlist are implemented.
Live peer gossip discovery is implemented for registered/bootstrap peers.
Signed validator checkpoint votes, local quorum evaluation, and the versioned
devnet consensus spec/hash are implemented. Public-mainnet consensus rules still
need testnet validation and external review.

## Daemon Cutover Phases

1. Read-only daemon: complete for local devnet inspection.
2. Write daemon: wallet registration, faucet, transfer, generic redemption, and
   catalog-backed product payment are implemented.
3. Fulfillment boundary: receipt records, historical receipt backfill, and
   review/contact/fulfillment status events are implemented. Next move
   tax/shipping rules and final fulfillment automation out of `app.py`.
4. Mempool: signed transaction queueing, pending inspection, balance reservation,
   and operator mining are implemented.
5. Block production: deterministic local block batches, ordered txid roots,
   Merkle transaction inclusion proofs, block versioning, and producer
   identity/seals are implemented.
6. Node boundary: local node identity, chain manifests/snapshots, snapshot
   verification, peer registry, peer manifest fetch, peer snapshot checks, and
   preview-only sync candidates are implemented. Guarded append-only chain
   import with backup/rollback is implemented. Explicit append-only fork-choice
   scoring, bootstrap peer config, and producer allowlists are implemented.
   Live peer gossip discovery and signed checkpoint vote quorum checks are
   implemented. Next validate broader consensus rules through public testnet
   operations and external review.
7. Wallet standard: encrypted browser backup envelope, hashed wallet
   recovery/custody policy, and wallet custody evidence verifier are
   implemented. Next complete reviewer-approved recovery phrase support, final
   address versioning, hardware wallet support, and approved custody
   operations.
8. Monetary policy: fixed devnet supply, treasury/faucet boundary, fee defaults,
   and tokenomics manual gates are hash-pinned for review. Next approve public
   distribution, treasury governance, fee/burn policy, and legal disclosures.
9. Genesis boundary: historical devnet state, clean candidate state, and any
   future reviewed mainnet allocation are separated by a hash-pinned genesis
   plan. Next approve allocation file totals, distribution basis, and treasury
   controls.
10. Security gate: machine-readable readiness gates, clean signed-only candidate
   ledger generation, consensus spec hashing, monetary policy hashing, genesis
   plan hashing, wallet policy hashing,
   public-testnet package generation, local multi-node testnet rehearsal,
   external security-review packet generation, security-review evidence
   verifier, legal/compliance evidence verifier, wallet custody evidence
   verifier, production deployment evidence verifier, mainnet decision
   verifier, reviewable
   release bundles with copied manual-gate docs, core regression tests, daemon
  product-payment route tests, repeatable smoke coverage, release manifests,
  genesis allocation verifier, manual gate evidence verifier, public testnet
  evidence verifier, threat model, and mainnet gate docs are implemented. Next expand
   UI/import/deployment coverage, execute external review, and run a public
   testnet.

## Production Boundary

This is not mainnet, a public consensus network, an exchange-listed asset, or an
investment product. Production launch still requires node software, consensus,
wallet/key custody decisions, audits, terms, and legal/compliance review.

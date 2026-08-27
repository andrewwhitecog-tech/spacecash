# SpaceCash Public Testnet Runbook

Current operator handoff packet: `PUBLIC_TESTNET_OPERATOR_HANDOFF_2026-06-10.md`.

## Entry Criteria

- Candidate bundle has verified checksums.
- Candidate ledger has no automated readiness blockers.
- Bootstrap peer list is defined and reviewed.
- Validator enrollment and quorum rules are written.
- Monitoring endpoints and incident contacts are prepared.

Generate the package:

```powershell
tools\nsp_python.cmd tools\spacecash_consensus_spec.py --out _tmp\spacecash_consensus_spec.json
tools\nsp_python.cmd tools\spacecash_monetary_policy.py --out _tmp\spacecash_monetary_policy.json
tools\nsp_python.cmd tools\spacecash_genesis_plan.py --out _tmp\spacecash_genesis_plan.json
tools\nsp_python.cmd tools\spacecash_genesis_allocation.py --template-out _tmp\spacecash_genesis_allocation_template.json
tools\nsp_python.cmd tools\spacecash_genesis_allocation.py --verify _tmp\spacecash_genesis_allocation_template.json
tools\nsp_python.cmd tools\spacecash_wallet_policy.py --out _tmp\spacecash_wallet_policy.json
tools\nsp_python.cmd tools\spacecash_testnet_plan.py --out-dir _tmp\spacecash_testnet_plan --force
tools\nsp_python.cmd tools\spacecash_operator_onboarding.py --verify _tmp\spacecash_testnet_plan --out _tmp\spacecash_testnet_plan\operator_onboarding_check.json
tools\nsp_python.cmd tools\spacecash_public_testnet_evidence.py --template-out _tmp\spacecash_public_testnet_evidence_template.json
tools\nsp_python.cmd tools\spacecash_public_testnet_evidence.py --verify _tmp\spacecash_public_testnet_evidence_template.json
tools\nsp_python.cmd tools\spacecash_public_testnet_evidence.py --workbench-out-dir _tmp\spacecash_public_testnet_workbench --force
```

The consensus, monetary, genesis, allocation, and wallet commands write the
current devnet spec/hash, supply policy/hash, allocation boundary/hash,
allocation template/check, and wallet policy/hash. The testnet package writes a
clean multi-validator candidate DB, three node configs, operator checklist,
`operators/` onboarding packet, daily report template, incident log, per-node
report templates, per-scenario evidence templates, a seeded public-testnet exit
evidence JSON, `operator_onboarding_check.json`, manual-gate evidence template,
public-testnet review workbench, and SHA256 checksums. These are preparation
evidence only; reviewers still need to run and accept the actual public testnet.

After the public testnet is actually run, the completed exit evidence must pass:

```powershell
tools\nsp_python.cmd tools\spacecash_public_testnet_evidence.py --verify _tmp\spacecash_public_testnet_evidence.json --require-complete
```

Run a local rehearsal:

```powershell
tools\nsp_python.cmd tools\spacecash_testnet_rehearsal.py --out-dir _tmp\spacecash_testnet_rehearsal --force
```

The rehearsal starts temporary local nodes from the package, verifies health,
readiness, manifests, audits, checkpoint quorum, bootstrap peer checks, gossip,
and sync previews, then writes `rehearsal_report.json`. This catches packaging
and node-route regressions before the public testnet, but it is not a substitute
for independently operated public nodes.

## Testnet Setup

1. Publish source hash, release bundle hash, and node setup instructions.
2. Start at least three independently operated nodes.
3. Configure bootstrap peers and peer identity labels.
4. Register validator wallets and quorum policy.
5. Complete `operators/contact_roster_template.md`, each
   `operators/node-*/operator_intake.json`, and each node runbook before the
   testnet opens.
6. Run faucet, signed transfer, product-payment, checkpoint, snapshot, gossip,
   sync-preview, and guarded import scenarios.
7. Archive daily audit, readiness, peer, and checkpoint reports.
8. Fill `reports/<node-id>/*.json`, each
   `operators/node-*/evidence_manifest_template.json`, and
   `evidence/scenarios/*.json`.
9. Copy `public_testnet_exit_evidence_template.json` to the final evidence path
   and complete it only after real operator evidence is attached.
10. Re-run
    `tools\nsp_python.cmd tools\spacecash_operator_onboarding.py --verify _tmp\spacecash_testnet_plan --require-complete`
    and archive the passing output before asking reviewers to accept
    `public_testnet_complete`.
11. Fill the workpapers in `_tmp\spacecash_public_testnet_workbench\testnet\`
    and use them to complete the final public-testnet evidence JSON.

## Exit Criteria

- No unresolved ledger integrity errors.
- No unsigned spend compatibility in the candidate chain.
- Any proposed launch allocation passes the allocation verifier in
  `--require-approved` mode.
- Validator checkpoint quorum remains healthy across node restarts.
- Peer sync previews classify same, ahead, behind, and diverged snapshots
  correctly.
- Incident log is reviewed and closed.
- Final testnet report is attached to the release bundle.
- Public-testnet evidence passes `--require-complete`.

## Rollback

If any consensus, wallet, or sync bug can cause loss of funds, fork confusion,
or unrecoverable keys, stop the testnet, archive the state, and produce a new
candidate bundle after remediation.

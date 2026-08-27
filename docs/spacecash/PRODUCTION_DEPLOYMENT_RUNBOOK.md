# SpaceCash Production Deployment Runbook

Current operator handoff packet: `PRODUCTION_DEPLOYMENT_OPERATOR_HANDOFF_2026-06-10.md`.

## Entry Criteria

- Public testnet exit report is approved.
- External audit findings are closed or formally accepted.
- Legal/compliance review clears the intended use.
- Monetary policy and treasury controls are approved.
- Genesis allocation file passes `--require-approved`, and the migration
  boundary is approved.
- Wallet recovery and custody policy is approved.
- Release bundle checksums verify.
- Source hash is tied to a reviewed artifact.
- Final mainnet decision evidence is prepared and remains blocked until every
  gate-specific evidence file is complete.

Generate and verify the machine-readable deployment evidence template:

```powershell
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --template-out _tmp\spacecash_production_deployment_evidence_template.json
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --verify _tmp\spacecash_production_deployment_evidence_template.json
tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --template-out _tmp\spacecash_mainnet_decision_template.json
tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --verify _tmp\spacecash_mainnet_decision_template.json
```

Generate the reviewer workbench packet:

```powershell
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --workbench-out-dir _tmp\spacecash_production_deployment_workbench --force
```

Before the deployment gate can be accepted, the completed evidence file must
pass:

```powershell
tools\nsp_python.cmd tools\spacecash_production_deployment_evidence.py --verify _tmp\spacecash_production_deployment_evidence.json --require-complete
tools\nsp_python.cmd tools\spacecash_mainnet_decision.py --verify _tmp\spacecash_mainnet_decision.json --require-complete
```

The workbench writes `production_deployment_evidence_workbench.json`,
`production_deployment_evidence_workbench_check.json`, deployment decision
workpapers, control documents, environment and readiness-input templates, final
approval template, and `SHA256SUMS.txt`. These are preparation artifacts only;
the production deployment manual gate remains blocked until a final
reviewer-completed evidence file passes `--require-complete`.

## Deployment Steps

1. Freeze source and generate release bundle.
2. Verify `SHA256SUMS.txt`.
3. Archive `release_manifest.json`, `bundle_summary.json`, `monetary_policy.json`, `genesis_plan.json`, `genesis_allocation_check.json`, approved allocation JSON, and candidate DB.
4. Publish node setup instructions and bootstrap peer list.
5. Deploy bootstrap nodes with monitoring.
6. Deploy validator nodes and verify checkpoint quorum.
7. Enable public read routes behind production HTTP controls.
8. Enable write routes only after authentication, authorization, CORS, rate
   limiting, logging, and backup policy are verified.
9. Run live audit and readiness checks after deployment.
10. Re-run the aggregate mainnet decision verifier against the archived release
    manifest, checksum manifests, approved allocation, completed evidence files,
    and launch authorization.

## Rollback

- Stop public write routes.
- Preserve logs, DB snapshots, and peer manifests.
- Restore from the last verified backup if ledger integrity is affected.
- Publish incident status and remediation plan.
- Generate a new release bundle before resuming.

## Monitoring

- Ledger audit validity.
- Checkpoint quorum health.
- Bootstrap peer reachability.
- Mempool pending/rejected counts.
- Product order and fulfillment anomalies.
- Daemon error rate and rate-limit events.

# SpaceCash Genesis Plan

SpaceCash currently separates three states:

- Historical local devnet state in `spacecash_devnet.sqlite3`
- Clean signed-only candidate ledgers created by `tools/spacecash_candidate.py`
- Any future mainnet genesis allocation

Generate the machine-readable plan with:

```powershell
python tools\spacecash_genesis_plan.py --out _tmp\spacecash_genesis_plan.json
```

Generate and verify the allocation template with:

```powershell
python tools\spacecash_genesis_allocation.py --template-out _tmp\spacecash_genesis_allocation_template.json
python tools\spacecash_genesis_allocation.py --verify _tmp\spacecash_genesis_allocation_template.json
```

The plan is hash-pinned in protocol config, exposed by
`/api/spacecash/genesis/plan` and `/genesis/plan`, and included in the release
manifest, release bundle, and external security-review packet.

## Current Boundary

- Historical devnet balances do not automatically migrate to mainnet.
- Legacy claim-token compatibility is not accepted for a mainnet allocation.
- Candidate private keys are development artifacts and are not allowed for
  mainnet custody.
- A mainnet launch requires a fresh reviewed allocation file.
- The allocation total must exactly match the approved supply cap.
- `tools\spacecash_genesis_allocation.py --require-approved` must pass before
  any launch allocation is treated as complete.

## Required Mainnet Inputs

- Reviewed allocation file with address, amount, label, and basis
- Machine-verified allocation hash, no duplicate addresses, and exact supply cap
- Public distribution and treasury governance approval
- Wallet address version and recovery policy approval
- Legal/compliance approval for token/payment use
- Release manifest source hash and bundle checksums
- Production deployment and rollback procedures

## Mainnet Rule

This plan makes the devnet-to-mainnet boundary reviewable. It does not approve
an allocation, distribution, treasury process, or launch.

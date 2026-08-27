# SpaceCash Genesis Allocation Verifier

SpaceCash now has a machine-checkable genesis allocation template and verifier.
This is still not an approved mainnet allocation.

Generate the template:

```powershell
python tools\spacecash_genesis_allocation.py --template-out _tmp\spacecash_genesis_allocation_template.json
```

Verify an allocation file:

```powershell
python tools\spacecash_genesis_allocation.py --verify _tmp\spacecash_genesis_allocation_template.json
```

Require launch approval fields:

```powershell
python tools\spacecash_genesis_allocation.py --verify _tmp\spacecash_genesis_allocation.json --require-approved
```

## Schema Rules

- The file must bind `chain_id`, `genesis_plan_hash`, and
  `monetary_policy_hash`.
- Every row must include `address`, `amount_units`, `label`, `basis`, and
  `reviewer`.
- Every address must be a valid SpaceCash address.
- Duplicate addresses are rejected.
- `amount_units` must be a positive integer.
- The approved total must exactly equal the protocol supply cap.
- The canonical `allocation_hash` must match the file body.
- `--require-approved` fails unless approval fields and the legal/compliance
  manual gate are complete.

## Launch Rule

The empty template is allowed to validate structurally because it is a review
starting point. It is not launch-ready. A launch allocation must pass
`--require-approved`, be archived in the release bundle, and have human
legal/compliance, distribution, and treasury approval.

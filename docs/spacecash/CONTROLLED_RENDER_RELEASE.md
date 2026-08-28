# SpaceCash controlled production operations

SpaceCash is an integrated NorthStar Prime subsystem, not a standalone
customer product. The public production ledger is served through
`app.northstarprime.net`, uses chain ID `spacecash-mainnet-1`, runs the
`closed-loop-mainnet` profile, and reports NorthStar Prime as its system of
record.

This runbook documents the non-secret operating contract. Provider
credentials, host-specific paths, scheduler principals, and alert receipts
stay in the private NorthStar operations repository.

## Public evidence

The deployment exposes three read-only evidence endpoints:

- `https://app.northstarprime.net/health` proves the NSP application is serving;
- `https://app.northstarprime.net/api/spacecash/status` reports chain identity,
  NSP integration, and redacted durability evidence;
- `https://app.northstarprime.net/api/spacecash/readiness` reports mainnet
  readiness, audit validity, and blocker lists.

A healthy release reports:

- chain ID `spacecash-mainnet-1` and profile `closed-loop-mainnet`;
- mode `closed-loop non-monetary mainnet`;
- `system_of_record` equal to `NorthStar Prime` and `standalone_product` false;
- a valid ledger audit with no automated or manual blockers; and
- a verified backup, successful integrity check and restore probe, and no
  active durability failure.

The endpoints expose proofs, not private keys, filesystem paths, credentials,
or operator authority.

## Exact-commit releases

Commit-triggered auto-deploy is disabled. The production service has an
attached persistent disk and is released by explicitly selecting one exact
40-character Git commit SHA.

The private release guard fails closed unless:

- auto-deploy is off and no deployment is active;
- public health, status, and readiness proofs are green;
- disk-snapshot and runtime guards are green;
- the requested revision is an exact commit, not a branch head; and
- the operator supplies the controlled-release acknowledgement.

After the provider reports the deployment live, the guard repeats the public
proofs and confirms auto-deploy remains off. A source push by itself must never
replace the running production revision.

## Two-layer durability

SpaceCash uses two independent durability layers:

1. The application creates rotating SQLite backups on the attached persistent
   disk. Each backup is hashed, integrity-checked, audited, and restored into a
   temporary database as a real restore probe.
2. The hosting provider automatically snapshots the persistent disk daily. An
   hourly guard verifies at least two snapshots exist, the newest is no more
   than 36 hours old, and each newly verified application backup is captured
   within a 30-hour grace period.

Awaiting the next normal provider snapshot is a monitored state, not silent
success. Missing, stale, overdue, or malformed evidence changes the guard to
`attention_required` and fails the release preflight. Routine monitoring never
runs a destructive provider restore.

## Failure visibility

The NorthStar Runtime Guard runs as a one-shot task every five minutes and at
operator logon. The snapshot guard runs hourly and at logon. Both return real
exit codes, reject overlapping instances, start when available, and retry
failures.

The runtime guard appends machine-local receipts and emits Windows Application
events through source `NorthStarRuntimeGuard`:

| Event ID | Meaning |
| --- | --- |
| 101 | A service first failed |
| 102 | A failure persisted |
| 103 | A service recovered |
| 104 | A recovery action ran |
| 105 | A monitored milestone was reached |

When a provider snapshot first captures a newly verified application backup,
the transition emits one event 105. Repeated healthy checks do not repeat the
milestone.

## Non-monetary boundary

Operational readiness does not change product policy: SPACE cannot be bought,
sold, exchanged, cashed out, held in custody for users, or redeemed for
physical goods, services, or discounts. Any such change re-enters the legal,
security, custody, and deployment gates in `CLOSED_LOOP_MAINNET.md`.

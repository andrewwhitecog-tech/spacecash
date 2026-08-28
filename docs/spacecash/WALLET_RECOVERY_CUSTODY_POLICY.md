# SpaceCash Wallet Recovery And Custody Policy

Current reviewer handoff packet: `WALLET_CUSTODY_REVIEWER_HANDOFF_2026-06-10.md`.

## Current State

SpaceCash browser wallets use signed P-256 spends and encrypted browser backup
JSON. The NSP production profile is user-controlled and non-custodial: the
server does not hold or recover user private keys. This design is not
authorization to offer custody.

Generate the machine-readable wallet policy:

```powershell
tools\nsp_python.cmd tools\spacecash_wallet_policy.py --out _tmp\spacecash_wallet_policy.json
```

The policy publishes `id`, `version`, and `policy_hash` for release bundles,
auditors, and operators. It is a review artifact, not custody approval.

Generate and verify the machine-readable wallet custody evidence template:

```powershell
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --template-out _tmp\spacecash_wallet_custody_evidence_template.json
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --verify _tmp\spacecash_wallet_custody_evidence_template.json
```

Generate the reviewer workbench packet:

```powershell
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --workbench-out-dir _tmp\spacecash_wallet_custody_workbench --force
```

Before the wallet custody gate can be accepted, the completed evidence file must
pass:

```powershell
tools\nsp_python.cmd tools\spacecash_wallet_custody_evidence.py --verify _tmp\spacecash_wallet_custody_evidence.json --require-complete
```

The workbench writes `wallet_custody_evidence_workbench.json`,
`wallet_custody_evidence_workbench_check.json`, decision workpapers, control
documents, final-approval template, and `SHA256SUMS.txt`. These are preparation
artifacts only; the wallet recovery/custody manual gate remains blocked until a
final reviewer-completed evidence file passes `--require-complete`.

## Current Controls

- Browser wallets sign with ECDSA P-256 over canonical JSON.
- Server private-key storage is not required for normal signed spends.
- Encrypted backups use the versioned `spacecash-encrypted-wallet-backup`
  envelope, PBKDF2-SHA256-250000, AES-256-GCM, and a minimum 12-character
  passphrase in the browser flow.
- Development candidate private keys are excluded from release/testnet bundles
  by default and are labeled unsafe when explicitly exported.

## Required Before Custody Or Monetary Expansion

- Recovery phrase or equivalent deterministic key recovery standard.
- Final address versioning and chain-specific replay/migration policy.
- Backup rotation policy.
- Lost-key and compromised-key procedures.
- Hardware wallet or custody plan.
- User-facing backup verification flow.
- Clear statement that the server never needs private keys for normal spends.

## Minimum User Warnings

- Lost private keys can mean permanent loss of access.
- Weak backup passphrases weaken encrypted exports.
- Browser profile compromise can compromise local wallets.
- Development candidate keys are never production custody keys.

## Operational Controls

- Private keys must not be committed, bundled by default, logged, or sent to the
  server.
- Any development key export must be explicitly requested and labeled as unsafe
  for custody.
- Custody support requires a separate legal, security, and operational review.

# SpaceCash Monetary Policy

SpaceCash currently has a deterministic devnet monetary policy artifact:

```powershell
python tools\spacecash_monetary_policy.py --out _tmp\spacecash_monetary_policy.json
```

The policy is hash-pinned in `spacecash_core.protocol`, exposed by
`/api/spacecash/monetary/policy` and `/monetary/policy`, and included in the
release manifest, release bundle, and external security-review packet.

## Current Devnet Rules

- Symbol: `SPACE`
- Decimals: `6`
- Base unit: `micros`
- Supply cap: current genesis supply
- Genesis allocation: current devnet supply starts in `SPACE-TREASURY`
- Block rewards: `0`
- Staking rewards: `0`
- Protocol transfer fee: `0`
- Mint route: not available
- Faucet source: treasury transfer only
- Checkout reference rate: devnet accounting only
- Symbolic overlay: `v + i*0x000999`, non-monetary metadata only

The ledger audit recomputes balances from transaction history and checks total
stored units against genesis supply. A clean mainnet candidate must not depend
on legacy unsigned spends.

## Symbolic Value Overlay

SpaceCash may carry the VORATH imaginary value marker in art, metadata, and
release artifacts:

```text
SpaceCash_value = v + i*sigma
sigma = 0x000999 = 2457
ledger_value = Re(v + i*sigma) = v
cash_value(i*sigma) = 0
```

This overlay has no accounting effect, no spendable value, no exchange value,
and no redemption value. It is a hidden symbolic design layer only.

## Mainnet Blockers

This document is not a public tokenomics approval. Before any mainnet claim,
SpaceCash still needs approved public distribution terms, treasury governance or
multisig controls, fee/burn/reward policy, market and tax disclosures, exchange
rate language, and legal/compliance signoff.

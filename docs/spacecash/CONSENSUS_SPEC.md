# SpaceCash Consensus Specification

SpaceCash currently publishes a versioned local-devnet consensus envelope, not a
public mainnet consensus protocol.

## Artifact

Generate the machine-readable specification with:

```powershell
python tools\spacecash_consensus_spec.py --out _tmp\spacecash_consensus_spec.json
```

The JSON contains `id`, `version`, and `spec_hash`. The same hash is exposed in
`python tools\spacecash_cli.py consensus-spec`, `GET /consensus/spec`,
`/api/spacecash/consensus/spec`, `python tools\spacecash_cli.py config`, and the
release bundle.

## Current Rules

- Signed wallet spends are ECDSA P-256 signatures over canonical JSON.
- Signed payloads bind `chain_id`, payload version, action, sender, recipient or
  product id, amount, and nonce.
- Pending mempool spends reserve sender balance before mining.
- Monetary policy hash pins current fixed-supply, treasury/faucet, and fee
  rules for review.
- Genesis plan hash pins the rule that mainnet must use a fresh reviewed
  allocation rather than mutated historical devnet state.
- Genesis allocation verifier output must reject malformed or unapproved launch
  allocations before any mainnet claim.
- Versioned blocks commit ordered txids through a SHA-256 Merkle root.
- New versioned blocks must be produced by a locally allowed producer id.
- Peer snapshots must verify digest, block hashes, supply, signatures, producer
  policy, and append-only extension before import.
- Fork choice is append-only only: a higher peer height imports only when the
  peer extends the local tip exactly.
- Diverged higher-scoring peers are reported but not automatically reorged.
- Checkpoint votes count only from locally registered validator wallets.

## Explicit Non-Goals

- No automatic reorgs.
- No public validator enrollment or rotation yet.
- No slashing or validator-removal rules yet.
- No authenticated peer identity or ban scoring yet.
- No economic finality or BFT consensus yet.
- No mainnet claim without public testnet evidence and external audit closure.

## Mainnet Rule

The consensus spec makes the current devnet rules reviewable. It does not remove
the remaining mainnet blockers in `MAINNET_GATE.md`.

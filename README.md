# SpaceCash

SpaceCash is an open-source experimental ledger and peer protocol for signed local-devnet transactions, deterministic blocks, checkpoint voting, audit proofs, and explicit release-readiness gates.

This repository is the standalone public reference implementation extracted from NorthStar Prime. Version `0.1.0` is a **development network**, not a public mainnet, security-audited cryptocurrency, investment, stablecoin, bank account, or promise of monetary value. Its default chain ID is `spacecash-devnet-1`; the daemon binds to loopback unless an operator deliberately changes it.

## What works

- SQLite-backed append-only ledger with deterministic block and chain manifests
- P-256 signed wallets and signed transfer/redeem payloads
- Merkle proofs, audit checks, peer snapshots, fork-choice previews, and guarded imports
- Mempool batching, producer policy, validator checkpoints, and quorum reporting
- HTTP daemon and command-line interface
- Machine-readable security, custody, legal, deployment, and mainnet decision gates

## Quick start

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[dev]"
pytest
spacecash status
spacecashd --host 127.0.0.1 --port 8876
```

In another terminal:

```bash
curl http://127.0.0.1:8876/health
curl http://127.0.0.1:8876/audit
curl http://127.0.0.1:8876/readiness
```

The default database is stored in the current user's application-data directory. Override it with `--db PATH` or `SPACECASH_DB`.

## Safety status

The readiness endpoint intentionally fails closed. A passing unit test suite establishes software behavior only; it does not establish legal approval, economic safety, operational custody, an external security audit, or public-mainnet readiness. See [MAINNET_GATE.md](docs/spacecash/MAINNET_GATE.md), [THREAT_MODEL.md](docs/spacecash/THREAT_MODEL.md), and [SECURITY.md](SECURITY.md).

Do not use real funds, private production credentials, regulated customer data, or irreversible value on this alpha devnet.

## License

Apache License 2.0. See [LICENSE](LICENSE).

# SpaceCash

SpaceCash is the open-source ledger engine integrated into NorthStar Prime for signed transactions, deterministic blocks, checkpoint voting, provenance, earned digital rewards, audit proofs, and explicit release-readiness gates.

The default profile remains the `spacecash-devnet-1` development network. The production profile is a deliberately non-monetary NorthStar closed loop, not a security-audited cryptocurrency, investment, stablecoin, bank account, legal tender, or promise of monetary value. The public repository is the reusable engine; NorthStar Prime is the product surface.

The production disclosure is: **SPACE is play money for the NorthStar universe. It cannot be bought, sold, or cashed out, and has no monetary value.** See [CLOSED_LOOP_MAINNET.md](docs/spacecash/CLOSED_LOOP_MAINNET.md).

## Live NSP mainnet

NorthStar Prime is the production system of record. Public read-only proofs:

- [application health](https://app.northstarprime.net/health)
- [SpaceCash status](https://app.northstarprime.net/api/spacecash/status)
- [SpaceCash readiness](https://app.northstarprime.net/api/spacecash/readiness)

The production chain is `spacecash-mainnet-1` under the
`closed-loop-mainnet` profile. The reusable engine is open source here; wallet,
arcade reward, operator-review, digital-sink, explorer, deployment, and alert
surfaces remain integrated into NorthStar Prime. See the
[controlled production operations runbook](docs/spacecash/CONTROLLED_RENDER_RELEASE.md).

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

Closed-loop mainnet requires explicit safety acknowledgements and an operator
token kept outside the repository:

```powershell
$env:SPACECASH_NETWORK_PROFILE = "closed-loop-mainnet"
$env:SPACECASH_MAINNET_ACK = "closed-loop-nonmonetary-v1"
$env:SPACECASH_DEPLOYMENT_ACK = "monitored-rollback-v1"
$env:SPACECASH_ADMIN_TOKEN = "<operator secret of at least 32 characters>"
spacecashd --host 127.0.0.1 --port 8877
```

Mainnet refuses legacy database relabeling, fiat purchase, public faucet,
server-generated claim-token wallets, and real-world product redemption.

In another terminal:

```bash
curl http://127.0.0.1:8876/health
curl http://127.0.0.1:8876/audit
curl http://127.0.0.1:8876/readiness
```

The default database is stored in the current user's application-data directory. Override it with `--db PATH` or `SPACECASH_DB`.

## Safety status

The readiness endpoint intentionally fails closed. A passing unit test suite establishes software behavior only; it does not establish legal approval, economic safety, operational custody, or an external security audit. The NSP-integrated non-monetary profile has separate runtime readiness and release controls. See [MAINNET_GATE.md](docs/spacecash/MAINNET_GATE.md), [THREAT_MODEL.md](docs/spacecash/THREAT_MODEL.md), and [SECURITY.md](SECURITY.md).

Do not use real funds, private production credentials, regulated customer data,
or irreversible value with SpaceCash. The production profile is deliberately
non-monetary and closed-loop.

## License

Apache License 2.0. See [LICENSE](LICENSE).

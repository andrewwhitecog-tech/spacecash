# Contributing

Contributions are welcome through issues and pull requests.

1. Keep changes compatible with the `spacecash-devnet-1` protocol unless the proposal explicitly introduces a new chain ID.
2. Add tests for consensus, signature, serialization, persistence, or API behavior changes.
3. Run `python -m pytest` before opening a pull request.
4. Never commit private keys, wallet exports, live databases, credentials, or personal data.
5. Treat changes to monetary policy, genesis state, signatures, fork choice, or readiness gates as security-sensitive and document their migration impact.

By contributing, you agree that your contribution is licensed under Apache-2.0.

# QUANTUM GENESIS — something from nothing, done honestly
*2026-07-19. Companion to SYMBOLIC_VALUE.md and GENESIS_PLAN.md. Module: `spacecash_core/quantum_entropy.py`. First light: `first_light_certificate.json` (context `spacecash-first-light`, 2026-07-19T09:53:08Z).*

## The physics, stated straight
- The quantum vacuum is not empty. The electromagnetic field's ground state carries irreducible **zero-point fluctuations** — this is textbook QED, measured routinely.
- The ANU QRNG points a homodyne detector at that vacuum state and measures those fluctuations. The resulting bits are **genuinely indeterminate before measurement** — per quantum mechanics they did not exist as facts until the detector fired. That is information *created*, not copied.
- What this is NOT: energy or matter from nothing. Conservation laws hold; vacuum "free energy" is pseudoscience and SpaceCash claims none of it. The honest claim is precise: **each ceremony artifact's uniqueness is born from a measurement of the vacuum — the physically real edge of "something from nothing."**

## What the module does
`generate(out_len, context)` →
1. draws 64 bytes of **local OS entropy** (always),
2. fetches vacuum-fluctuation bytes from ANU (free endpoint, or keyed via `SPACECASH_QRNG_API_KEY`),
3. mixes via `sha512-expand(local || vacuum || context || counter)`,
4. emits entropy + a **birth certificate**: source, UTC time, SHA-256 of the raw vacuum bytes, mix spec, and a commitment hash of the output.

## Security invariants (non-negotiable)
1. **Vacuum bytes never used alone.** A compromised or observed QRNG cannot weaken the output below local-entropy strength.
2. **Never consensus-critical.** Consensus stays deterministic per CONSENSUS_SPEC. Quantum entropy is for *ceremonies and identity*, not fork choice, not block validity.
3. **Offline-honest.** No vacuum reachable → provenance says `local_only`. The chain never lies about where its bits were born.

## Where it plugs in (ceremony surfaces, no ledger surgery)
| Surface | Use |
|---|---|
| **Genesis ceremony** | Mainnet genesis seed material generated with a public birth certificate — "SPACE was seeded from the vacuum on <date>," auditable by hash. |
| **Ceremony nonces** | Checkpoint/epoch commemoration values (non-consensus metadata). |
| **Wallet birth certificates** | Optional: new wallets record a vacuum-seeded ID + certificate — every wallet provably unique from the vacuum. Collectible/lore surface (VORATH: the Drift breathes through the vacuum). |
| **Symbolic value** | SYMBOLIC_VALUE.md gains its physical anchor: scarcity + uniqueness rooted in measured quantum indeterminacy. |

## Launch reality (unchanged by any of this)
Engineering is devnet-complete with **0 automated blockers**. The 5 remaining gates are human by design and stay that way: independent public testnet, external security review, legal/compliance, wallet-custody signoff, production-runbook approval (see LAUNCH_STATUS_REPORT.md). Quantum Genesis adds meaning and auditability; it does not — and must not — shortcut a single gate.

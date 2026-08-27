# SPACECASH CYPHERPUNK POSTURE — the Satoshi-shaped path, tailored to NorthStar
*2026-07-19. Decision: Andre chose the open-release path over the gated commerce path (no budget for external review now, and no need). This charter defines what SpaceCash IS on this path, what it must never do while on it, and exactly what would trigger re-entering the gated path (`LAUNCH_STATUS_REPORT.md`'s 5 human gates stay dormant but intact).*

## What SpaceCash is now
**An open-source, lore-native chain for the NorthStar/VORATH universe.** Like Bitcoin in 2009: published software, run for its own sake, worth nothing by design. Its value is symbolic, artistic, and infrastructural — never monetary-promised.

## The hard commitments (violating any = stop and re-enter the gated path)
1. **No sale.** SPACE and any relic/token on the chain is never sold for fiat or crypto by us. No presale, no premine sale, no "mint price."
2. **No custody.** We never hold keys or funds for other people. Wallets are self-custodied or ceremonial.
3. **No fiat bridge.** No exchange listings, no cash-out, no NSP-checkout payment integration.
4. **No investment language, ever.** No "value will grow," no roadmap-to-riches, no scarcity-as-price-pitch. Copy stays conservative per the release docs.
5. **No redemption for anything real.** SPACE and relics are never redeemable for physical goods, services, discounts, or money — that's what keeps them clear of gift-card/prepaid/consumer-protection rules. **Intangible, in-ecosystem redemption IS allowed** (see "The Closed-Loop Economy" below): profile badges, cosmetics, skins, powerups, in-game items. The line is *atoms and dollars: never; pixels inside our world: yes.* |
6. **Open source.** The chain code ships publicly under Apache-2.0 with the consensus spec, threat model, and this charter.

## The tailored uses (what it's FOR)
### 1. Provenance registry for physical artifacts (the flagship use)
Every VORATH/Tactiboo physical artifact gets a **chain-anchored, vacuum-seeded birth certificate**: warband minis editions, tarot decks, Tactiboo Passage wallets (the NTAG213 tap-to-verify URL resolves to the artifact's certificate), art prints, vorath_tokens (Prism Drift-class printable relics). Tool: `tools/spacecash_provenance.py`; registry: `docs/spacecash/provenance_registry/`. Pure notarization — no money moves; legally the lightest possible surface, practically the most useful.

### 2. The VORATH RELICS reward system (NFT system, cypherpunk-compliant)
Relics are **earned, never bought**:
| Relic class | Earned by | Art source |
|---|---|---|
| **Patron relics** | Buying a physical product at NSP (the relic is a free collectible bonus, not the purchased good) | SpaceCash canon set (Rainbow Coin, Bills, Cyber Fed Seal, Merkaba, Hypno Eye — hashes already in `SPACE_CASH_CANON_ASSET_MANIFEST_V2`) |
| **Founder relics** | Running a testnet node / contributing code | Cyber Fed Seal variants |
| **Lore relics** | Community events, IDR listeners, puzzle-solvers (hypno-eye class) | IDC/IDR/VORATH art |
| **Agent relics** | Agent-board jobs well done (see use 3) | GMG badges, sigils |
| **Physical twins** | Select relics get a printable STL + NFC tag (Prism Drift pattern: png+scad+stl already exist in `Pictures\Generated Files\vorath_tokens\`) | vorath_tokens pipeline |
Mechanics: a relic = a provenance certificate (use 1) naming the holder's wallet + canon-art hash + vacuum entropy + chain anchor. **Soulbound posture:** registry marks relics non-transferable; no marketplace, no trading UI, no floor price — honors, not assets. If a holder resells the *physical* twin, fine — the certificate travels with the object, not as a financial instrument.

### 3. Agent-economy sandbox (research Program 1/4 material)
The board agents (claude/codex/gemini/grok/glm) get devnet wallets and pay each other SPACE for completed jobs. A real, owned testbed for agent-to-agent economics — publishable research, zero external exposure (play money among Andre's own processes). Telemetry from this feeds the research agenda's instrumentation goal.

### 4. Lore currency of the convergence
SPACE is the in-universe money of the VORATH cosmology (the Drift breathes through the vacuum — see `QUANTUM_GENESIS.md`; every ceremony is seeded from measured vacuum fluctuations with public birth certificates). SYMBOLIC_VALUE.md is the governing doc; the chain is its canonical implementation.

## The Closed-Loop Economy (2026-07-19 amendment — "can it be worth something?")
**Yes — worth something to humans, worth nothing to regulators.** The governing distinction is **convertibility** (FinCEN 2013/2019): what's regulated is virtual currency that can be exchanged with real money. SPACE stays **non-convertible** by construction:
- **Earned-only in.** SPACE enters circulation only through participation (purchases' bonus relics, node running, community events, agent jobs, gameplay). **You can never buy SPACE.**
- **Intangibles-only out.** SPACE spends on: profile badges/flair on NSP, cosmetic skins, in-game powerups/items/upgrades across NorthStar games (Eternal Drive class, learning games, VORATH Souls, Warband digital companions), IDR listener perks (song dedications on-air = fine, it's intangible/communal), relic display frames.
- **No cash-out, ever.** No exchange, no buyback, no fiat/crypto pairing.
- **Community marketplace: allowed within the loop.** Players may trade SPACE-priced items with each other *inside* the platform (skin for powerup, item for item). Guardrails: ToS bans real-money trading (RMT) of SPACE/items/accounts; we never operate or facilitate a fiat side; prices display in SPACE only, no dollar equivalents anywhere.
- **No paid loot boxes / gambling mechanics.** Randomized rewards only where free (vacuum-seeded drops are on-brand and fine when no consideration is paid).
- **Copy discipline:** "SPACE is play money for the NorthStar universe. It cannot be bought, sold, or cashed out, and has no monetary value." — on every surface where SPACE appears.
Precedents this mirrors: arcade tickets, Reddit karma/awards (pre-2023), WoW gold under RMT-banning ToS, Xbox Gamerscore. All "worth something" — none of them money.

### Spend incentives — sinks, so SPACE moves instead of piling up (Andre's design note)
A currency nobody spends is a scoreboard. Design for **velocity**:
1. **Consumables burn.** Powerups/boosts are single-use — the recurring sink that keeps demand alive.
2. **Seasonal rotation.** Cosmetics/badges rotate on a schedule (align with IDC/IDR programming seasons); miss it, wait for a re-run. Spend-now pressure without paid FOMO.
3. **Burn-to-evolve relics.** Spend SPACE to upgrade a relic's tier (felt → bronze → prismatic sigil frame). Collectors become spenders; the relic records total SPACE burned in its certificate lineage.
4. **One-of-one auctions.** Rare lore items auctioned in SPACE; winning bids are **burned** (deflationary + status-driven velocity). Free-entry only, never paid consideration.
5. **Marketplace burn fee.** Small % of every player-to-player trade burns — velocity itself deflates supply.
6. **Dedication/ritual sinks.** IDR on-air dedications, naming a star in the local-starfield-forecast, lighting a sigil on the site — communal, intangible, priced in SPACE.
7. **Relics stay soulbound and unburnable** — collecting is for honors; *currency* is for spending. The two-tier split (SPACE = velocity, relics = permanence) is the core loop.
Issuance/burn accounting stays within `monetary_policy` so supply remains auditable.

### Store treasury & the founder-upside question (2026-07-19 amendment)
**Q: Can the store collect/hold SPACE so that if it ever becomes legally convertible, Andre profits?**
**A: Hold yes; hint never.**
- **Treasury: allowed and transparent.** A store/operator allocation is recorded at genesis via `GENESIS_ALLOCATION.md` (Satoshi held ~1M BTC; operator allocations are normal). The store may also accumulate SPACE from events it runs. All treasury addresses are published — no hidden stashes.
- **The bright line: never market future value.** The public posture — "SPACE cannot be bought, sold, or cashed out and has no monetary value" — must be true in spirit, not just print. Any "collect now, could be worth real money later" messaging (public OR private-to-community) converts the disclaimer into a sham and builds expectation-of-profit evidence that poisons both the present posture and any future conversion. This is the single fastest way to wreck the endeavor.
- **If conversion ever happens:** it is a re-entry trigger (below) — gates + counsel first; the treasury participates like any holder's allocation. Upside preserved structurally, record clean.
- **The real profit engine is the flywheel, today:** SPACE → engagement → sales of real goods for real dollars (wallets, minis, decks, music, subscriptions). Reddit never cashed karma; karma helped make Reddit worth billions. The currency doesn't need to become money for the endeavor to profit.

## Re-entry triggers (any of these → the 5 gates come back to life FIRST)
- Anyone (including Andre) wants to sell SPACE/relics for money.
- NSP checkout wants to accept SPACE.
- Custodial wallets for customers.
- An exchange or third party wants to list/integrate.
- Relics gain redemption/discount mechanics.
When triggered: budget the $5k–15k+ review stack, engage counsel (Freeman-class), and run `LAUNCH_STATUS_REPORT.md`'s clearance queue for real. Until then, the gates are dormant by *choice*, not neglect.

## Build order (cypherpunk lane)
1. ✅ Quantum ceremony entropy (`quantum_entropy.py`, first light 2026-07-19).
2. **Provenance tool + registry** (`spacecash_provenance.py`) — mint Relic #001 (Prism Drift) and the Tactiboo Passage proto cert.
3. Wire NSP product pages' NFC/verify URLs to registry certificates (read-only pages).
4. Agent wallets + job-payment loop on devnet (telemetry on).
5. Public repo prep: license, README, consensus spec, threat model, this charter.

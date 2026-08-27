# SpaceCash Closed-Loop Mainnet

This is the executable NorthStar product profile chosen on 2026-07-19. It is a
non-monetary production chain for provenance, earned participation rewards,
games, profiles, relics, and other NorthStar digital experiences.

The required public disclosure is:

> SPACE is play money for the NorthStar universe. It cannot be bought, sold,
> or cashed out, and has no monetary value.

## Code-enforced boundaries

When `SPACECASH_NETWORK_PROFILE=closed-loop-mainnet`:

- the chain ID is `spacecash-mainnet-1`;
- genesis is deterministic and devnet databases cannot be relabeled;
- SPACE cannot be purchased for fiat or crypto;
- the public faucet is disabled and distribution uses idempotent earned-reward events;
- physical-product, service, discount, cash, and exchange redemption paths fail closed;
- server-generated claim-token wallets are disabled; users register self-managed signed wallets;
- server custody, exchange integration, and investment marketing are prohibited;
- operator mutations require a separate daemon authorization token;
- the daemon binds to loopback unless an explicit reverse-proxy/firewall acknowledgement is present.

The profile is selected only with both acknowledgements:

```text
SPACECASH_MAINNET_ACK=closed-loop-nonmonetary-v1
SPACECASH_DEPLOYMENT_ACK=monitored-rollback-v1
```

These are safety interlocks, not secrets. `SPACECASH_ADMIN_TOKEN` is a secret
and must be at least 32 characters, remain outside the repository, and be
available only to the NSP operator service.

## Re-entry triggers

The fuller commerce gates immediately become blockers before any of the
following:

- selling SPACE or relics for fiat or crypto;
- cash-out, buyback, exchange listing, or an external price pair;
- custody or recovery of another person's private key;
- accepting SPACE for physical goods, services, or discounts;
- marketing expected profit or future monetary value.

## Regulatory evidence boundary

This profile reduces facts associated with a monetary or investment product;
it is not a legal opinion or universal exemption. FinCEN says regulatory
treatment depends on facts and circumstances and defines convertible virtual
currency as value that has an equivalent currency value or acts as a substitute
for currency. Its guidance also distinguishes user-controlled from hosted
wallets. The SEC's March 2026 interpretation separately analyzes crypto assets
and the transactions or schemes around them. California's Digital Financial
Assets Law and final regulations are now in effect and must be rechecked before
changing the product facts.

Primary sources, checked 2026-08-27:

- FinCEN FIN-2013-G001: https://www.fincen.gov/resources/statutes-regulations/guidance/application-fincens-regulations-persons-administering
- FinCEN FIN-2019-G001: https://www.fincen.gov/sites/default/files/2019-05/FinCEN%20Guidance%20CVC%20FINAL%20508.pdf
- 31 CFR 1010.100: https://www.ecfr.gov/current/title-31/subtitle-B/chapter-X/part-1010/section-1010.100
- SEC Release 33-11412, effective 2026-03-23: https://www.sec.gov/rules-regulations/2026/03/s7-2026-09
- California DFPI final DFAL regulations, effective 2026-06-29: https://dfpi.ca.gov/rules-enforcement/laws-and-regulations/digital-financial-assets-law-regulations-opinions-releases/

## Honest launch language

`mainnet` means the canonical production ledger for this non-monetary
NorthStar use. It does not mean audited money, legal tender, an investment,
an exchange-listed asset, a bank account, or a promise of value. Independent
node testing and external security review remain published advisories and
become mandatory before any commerce re-entry trigger.

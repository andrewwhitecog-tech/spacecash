# SpaceCash Symbolic Value

SpaceCash now has a deterministic non-monetary symbolic artifact:

```powershell
python tools\spacecash_symbolic_value.py --out _tmp\spacecash_symbolic_value.json
```

Embed the same code into curated SpaceCash artwork with:

```powershell
python tools\spacecash_embed_symbolic_art.py
```

That command backs up the original curated PNGs under
`static/curated/spacecash/_pre_symbolic_000999_backup/`, then redraws the live
bill, coin, and wallpaper assets with microtext, rim ticks, guilloche rhythm,
and PNG text metadata.

This artifact encodes the VORATH `000 = 999` axis into SpaceCash without changing
ledger balances, supply, checkout math, or redemption value.

## Core Formula

```text
SpaceCash_value = v + i*sigma
```

Where:

- `v` is the real spendable ledger value.
- `i*sigma` is the imaginary symbolic value.
- `sigma = 0x000999 = 2457`.

The accounting rule is:

```text
ledger_value = Re(v + i*sigma) = v
cash_value(i*sigma) = 0
```

So the imaginary component is the hidden valueless value: meaningful as art,
lore, metadata, and easter egg, but not spendable and not redeemable.

## Canonical Encodings

```text
void:       000
overload:   999
collapse:   000999
hex:        0x000999
decimal:    2457
binary:     100110011001
octal:      4631
base36:     1W9
digital:    9
time mark:  retroactivelyforwardhencew()RTH
```

ASCII encodings:

```text
000=999 decimal: 48 48 48 61 57 57 57
000=999 hex:     30 30 30 3D 39 39 39
```

## Embedding Rules

Use `000999` as microtext, metadata, serial texture, guilloche rhythm, coin rim
ticks, bill linework, manifest fields, filenames, and creator-facing prompts.
Use `retroactivelyforwardhencew()RTH` as the internal cue that older and future
VORATH assets can inherit the same symbolic code without altering accounting.

Do not present `000999`, `2457`, `1W9`, or `i*sigma` as spendable value,
investment value, exchange value, or a redemption promise.

The actual monetary value stays in the real component:

```text
actual_value = v
imaginary_value = i*0x000999
redeemable_value = v
```

## Design Read

Plain English:

> SpaceCash has real devnet ledger value for accounting, and an imaginary VORATH
> value hidden inside the design. The imaginary value is deliberately valueless:
> it exists as a symbol of the void-overload collapse, not as money.

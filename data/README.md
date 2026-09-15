# data

written by the [daily workflow](../.github/workflows/daily.yml) at 00:43 utc: the last hour of blocks
(`builderwatch --since 1h`), one row per builder.

`daily.csv` columns:

- `date_utc`: the date of the last block in the window
- `from_block`, `to_block`, `blocks`: the window; `slots_missed`: the 12-second slots inside it that got no block
  (the same number on every row of a day, it belongs to the window)
- `builder`: the short name from the table in `builderwatch/builders.py`, `no builder` for the blocks validators
  built themselves, or the extra data as it is for a name the table does not know
- `blocks_built`, `share`: of the blocks in the window (a fraction, 0.53 is 53%)
- `gas_used_mean`: how full this builder's blocks were, gas used over gas limit
- `base_fee_median_gwei`: the median base fee of this builder's blocks
- `fee_recipient`: the address this builder's blocks paid most often

a rerun for the same day replaces that day's rows. columns are only ever appended.

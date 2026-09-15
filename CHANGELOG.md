# changelog

all notable changes to builderwatch. the format follows [keep a changelog](https://keepachangelog.com/en/1.1.0/),
versions follow [semver](https://semver.org/) as far as a command line tool has an api.

## [0.1.0] - 2026-09-15

first cut: who built the last blocks, from the headers.

- the builder of every block from its extra data, matched against a table with a source on every line; unknown
  names shown as they are, local blocks named by the execution client that made them
- the fee recipient from the header
- the slots that got no block, from the timestamps
- the table, `--json`, `--csv` with one row per block, `--since 6h`, and a daily workflow that writes `data/daily.csv`

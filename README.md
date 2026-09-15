# builderwatch

[![ci](https://github.com/alinaschanz/builderwatch/actions/workflows/ci.yml/badge.svg)](https://github.com/alinaschanz/builderwatch/actions/workflows/ci.yml)
![python 3.10+](https://img.shields.io/badge/python-3.10%2B-3776ab)
![license mit](https://img.shields.io/badge/license-MIT-2b7a74)
[![release](https://img.shields.io/github/v/release/alinaschanz/builderwatch?color=2b7a74)](https://github.com/alinaschanz/builderwatch/releases)
[![openssf scorecard](https://api.scorecard.dev/projects/github.com/alinaschanz/builderwatch/badge)](https://scorecard.dev/viewer/?uri=github.com/alinaschanz/builderwatch)

who built the last blocks of ethereum. every block header carries 32 bytes of `extraData`, and a
builder writes its name there; a validator that builds its own block leaves whatever its client
puts there. read the last hour of headers from a public rpc, count, and the market for blocks is
one table. no keys, no relay api, no explorer.

```
$ builderwatch
who built the last 300 blocks: 25,982,343 to 25,982,642, 10:43 to 11:43 utc, 2026-09-15

builder          blocks  share   full  base fee  fee recipient
titan               168  56.0%  55.5%     0.065  0x4838…5f97    titanbuilder.xyz
quasar               49  16.3%  63.0%     0.063  0x3963…aa49    quasar.win
buildernet           28   9.3%  23.8%     0.062  0xdadb…3711    buildernet.org
no builder           20   6.7%  17.0%     0.065  15 addresses   validators' own nodes: (empty) x5, geth 1.17.3 x4, geth 1.17.5 x3
eureka               17   5.7%  65.1%     0.062  0xfb74…571b    eurekabuilder.xyz
bombora              12   4.0%  45.6%     0.067  0x85c2…cb33    bombora.build
bob the builder       3   1.0%  20.2%     0.067  0xd87f…4d96    bobthebuilder.xyz
bitget                1   0.3%   8.1%     0.066  0x1d5b…00dc    bitget.com
builder+              1   0.3%  34.0%     0.073  0x400b…8485    btcs.com/builder
.                     1   0.3%  11.8%     0.066  0x7d0a…0474    unknown, the extra data as it is

slots without a block: 3 of 303 (1.0%)
gas limit 60,000,000; the mean block was 50.6% full, 30.4m gas; median base fee 0.064 gwei; 81,038 transactions and 1,627 blobs in the window
share is of blocks built, not of slots. a block with a builder name in its extra data was bought through mev-boost;
"no builder" is a validator that built its own block with its execution client, named by that client.
```

two builders made 72% of the blocks in that hour, and the top five made 91%. the blocks validators
built themselves were 17% full against 55% for titan's: a builder fills a block with everything that
pays, a local node takes what its own mempool saw. three slots in the hour got no block at all.

## install

```
pipx install git+https://github.com/alinaschanz/builderwatch
```

or clone it and run `python -m builderwatch` from the folder. python 3.10 or newer, no dependencies.

## use

```
builderwatch                       # the last 300 blocks, about an hour
builderwatch --since 6h            # the blocks of the last six hours, found by bisecting timestamps
builderwatch --blocks 50
builderwatch --json                # the same, every number, the fee recipients and the client strings
builderwatch --csv blocks.csv      # one row per block: builder, extra data as text, recipient, gas, base fee, blobs
builderwatch --since 1h --summary-append data/daily.csv --quiet   # one row per builder, the dataset
builderwatch --rpc https://your.node
```

## how it works

- one `eth_getBlockByNumber` per block with transaction hashes only, twenty-five to a batch request,
  four batches in flight. an hour of headers is a few megabytes; two thousand blocks took 68 seconds
  from publicnode. endpoints publicnode, mevblocker, drpc, tenderly, blastapi in that order, or `--rpc`
  yours. the newest block is left out: it can still be reorganised, and a lagging endpoint may not
  have it.
- **names.** `extraData` is decoded as utf-8 and matched against a small table in
  [builderwatch/builders.py](builderwatch/builders.py): a needle, a short name, the builder's site,
  and where the line comes from (the first block of a 2,000-block sample on 2026-09-15, or the note
  that a 2023-2024 name did not show up in that sample). anything else is printed as the text it is, so a
  new builder appears as itself instead of as a wrong guess. the fee recipient is reported from the
  headers, not from a table: a builder pays itself, so the address next to the name is the builder's.
- **local blocks.** geth writes an rlp list `[version, "geth", "go1.26.4", "linux"]` by default; besu,
  nethermind, reth and erigon write a version string; some validators clear the field. those blocks
  are grouped under "no builder" with the clients that made them.
- **missed slots.** every block since the merge sits on a 12-second slot, so a 24-second gap between
  two blocks is one slot whose proposer produced nothing (or whose block was reorganised away). the
  count is gaps inside the window, from the header timestamps alone.
- **full** is gas used over gas limit; the base fee is the block's own.

## reading the table

- share is of the blocks in the window, not of all slots and not of value: a builder that wins
  half the blocks does not earn half the fees.
- a name in `extraData` is what the builder chose to write, and nothing stops anyone from writing
  someone else's. the fee recipient column is the harder fact: the address the block's fees went to.
- a validator whose relay returned no bid, or who runs without mev-boost, builds locally; a local
  block is not a worse block, it is a block that did not go through the auction.
- an hour is a sample. shares move by a few points from hour to hour; the [dataset](data/) keeps one
  hour a night for the longer view.

## the dataset

`data/daily.csv` gets one row per builder every night at 00:43 utc, from the last hour of blocks:
blocks, share, how full, the median base fee, the fee recipient, and the slots without a block. columns
are in [data/README.md](data/README.md); a rerun for the same day replaces the day.

## exit codes and scripting

`0` after a table, `2` when the window is empty, the duration does not parse or no rpc answered.
`--json` carries the builders with every fee recipient and every client string seen, so
`builderwatch --json | jq '.builders[] | select(.kind == "local")'` lists the self-built blocks.

## see also

- [blobwatch](https://github.com/alinaschanz/blobwatch): who bought the blob space in the same blocks
- [gasweek](https://github.com/alinaschanz/gasweek): the base fee those blocks charged, by hour of day
- the notes: [alinaschanz.life](https://alinaschanz.life), the short version on [x](https://x.com/alinaschanz)

## verify a release

every release carries the sdist and the wheel, a `SHA256SUMS` file, an opentimestamps proof of that
file, and a build provenance attestation made in github's own signing flow. with the files downloaded
into one folder:

    sha256sum -c SHA256SUMS
    gh attestation verify ./*.whl --owner alinaschanz
    ots verify SHA256SUMS.ots

the commit itself is [signed](https://alinaschanz.life/verify/#commits).

## license

[mit](LICENSE). numbers, not calls. not financial advice.

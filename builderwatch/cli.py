"""command line entry point: builderwatch [--blocks 300 | --since 1h] [--json] [--csv FILE] [--summary-append FILE]"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from datetime import datetime, timezone

from . import __version__
from .rpc import Rpc, RpcError, RpcUnavailable
from .scan import SLOT, Block, first_block_since, group, median_base_fee, missed_slots, scan

CSV_FIELDS = ("block", "time_utc", "builder", "kind", "extra_data", "fee_recipient", "gas_used", "gas_limit", "base_fee_wei",
              "blobs", "txs", "size")
SUMMARY_FIELDS = ("date_utc", "from_block", "to_block", "blocks", "slots_missed", "builder", "blocks_built", "share", "gas_used_mean",
                  "base_fee_median_gwei", "fee_recipient")


def parse_since(text: str) -> int:
    """'90m', '2h', '1d', '600s' -> seconds."""
    m = re.fullmatch(r"\s*(\d+)\s*([smhd])\s*", text.lower())
    if not m or int(m.group(1)) == 0:
        raise ValueError(f"not a duration: {text!r} (try 30m, 2h, 1d)")
    return int(m.group(1)) * {"s": 1, "m": 60, "h": 3600, "d": 86400}[m.group(2)]


def iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def short(address: str) -> str:
    return f"{address[:6]}…{address[-4:]}" if len(address) == 42 else address


def gwei(wei: float) -> str:
    return f"{wei / 1e9:.3f}" if wei >= 1e7 else f"{wei / 1e9:.4g}"


def summary(blocks: list[Block], rows) -> dict:
    slots = (blocks[-1].time - blocks[0].time) // SLOT + 1
    missed = missed_slots(blocks)
    return {
        "from_block": blocks[0].number, "to_block": blocks[-1].number, "blocks": len(blocks),
        "from_time_utc": iso(blocks[0].time), "to_time_utc": iso(blocks[-1].time),
        "slots": slots, "slots_missed": missed, "slots_missed_share": missed / slots if slots else 0.0,
        "gas_limit": blocks[-1].gas_limit, "gas_used_mean": sum(b.gas_used for b in blocks) / len(blocks),
        "full_mean": sum(b.full for b in blocks) / len(blocks), "base_fee_median_wei": median_base_fee(blocks),
        "txs": sum(b.txs for b in blocks), "blobs": sum(b.blob_gas_used // 131072 for b in blocks),
        "builders": [{"name": r.name, "site": r.site, "kind": r.kind, "blocks": r.blocks, "share": r.blocks / len(blocks),
                      "full_mean": r.full, "txs": r.txs, "blobs": r.blobs,
                      "base_fee_median_wei": int(sorted(r.base_fees)[len(r.base_fees) // 2]),
                      "fee_recipient": r.recipient, "recipients": r.recipients,
                      "extra_data": r.texts} for r in rows],
    }


def table(s: dict) -> str:
    lines = [f"who built the last {s['blocks']:,} blocks: {s['from_block']:,} to {s['to_block']:,}, "
             f"{s['from_time_utc'][11:16]} to {s['to_time_utc'][11:16]} utc, {s['to_time_utc'][:10]}", ""]
    lines.append(f"{'builder':<16} {'blocks':>6} {'share':>6} {'full':>6} {'base fee':>9}  {'fee recipient':<14}")
    for r in s["builders"]:
        who = short(r["fee_recipient"])
        note = r["site"]
        if r["kind"] == "local":
            clients = ", ".join(f"{k} x{v}" if v > 1 else k for k, v in sorted(r["extra_data"].items(), key=lambda kv: -kv[1])[:3])
            note = f"validators' own nodes: {clients}"
            if len(r["recipients"]) > 1:
                who = f"{len(r['recipients'])} addresses"
        elif r["kind"] == "unknown":
            note = "unknown, the extra data as it is"
        lines.append(f"{r['name'][:16]:<16} {r['blocks']:>6} {r['share']:>6.1%} {r['full_mean']:>6.1%} "
                     f"{gwei(r['base_fee_median_wei']):>9}  {who:<14} {note}")
    lines += ["", f"slots without a block: {s['slots_missed']} of {s['slots']} ({s['slots_missed_share']:.1%})",
              f"gas limit {s['gas_limit']:,}; the mean block was {s['full_mean']:.1%} full, "
              f"{s['gas_used_mean'] / 1e6:.1f}m gas; median base fee {gwei(s['base_fee_median_wei'])} gwei; "
              f"{s['txs']:,} transactions and {s['blobs']:,} blobs in the window",
              "share is of blocks built, not of slots. a block with a builder name in its extra data was bought through mev-boost;",
              "\"no builder\" is a validator that built its own block with its execution client, named by that client."]
    return "\n".join(line.rstrip() for line in lines)


def csv_rows(blocks: list[Block]) -> list[dict]:
    return [{"block": b.number, "time_utc": iso(b.time), "builder": b.builder.name, "kind": b.builder.kind, "extra_data": b.builder.text,
             "fee_recipient": b.recipient, "gas_used": b.gas_used, "gas_limit": b.gas_limit, "base_fee_wei": b.base_fee,
             "blobs": b.blob_gas_used // 131072, "txs": b.txs, "size": b.size} for b in blocks]


def summary_rows(s: dict) -> list[dict]:
    date = s["to_time_utc"][:10]
    return [{"date_utc": date, "from_block": s["from_block"], "to_block": s["to_block"], "blocks": s["blocks"],
             "slots_missed": s["slots_missed"], "builder": r["name"], "blocks_built": r["blocks"], "share": f"{r['share']:.4f}",
             "gas_used_mean": f"{r['full_mean']:.4f}", "base_fee_median_gwei": f"{r['base_fee_median_wei'] / 1e9:.6f}",
             "fee_recipient": r["fee_recipient"]} for r in s["builders"]]


def append_summary(path: str, rows: list[dict]) -> None:
    """one row per builder per utc date: a rerun on the same day replaces that day's rows."""
    existing: list[dict] = []
    if os.path.exists(path) and os.path.getsize(path):
        with open(path, newline="", encoding="utf-8") as f:
            existing = [r for r in csv.DictReader(f) if r.get("date_utc")]
    fresh = {r["date_utc"] for r in rows}
    merged = [r for r in existing if r["date_utc"] not in fresh] + rows
    merged.sort(key=lambda r: r["date_utc"])  # stable: within a day the rows stay in table order, most blocks first
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(merged)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="builderwatch",
                                 description="who built the last blocks of ethereum, from the extra data of their headers.")
    window = ap.add_mutually_exclusive_group()
    window.add_argument("--blocks", type=int, default=300, help="how many of the newest blocks (default 300, about an hour)")
    window.add_argument("--since", metavar="DURATION", help="the blocks of the last 30m, 2h, 1d instead")
    ap.add_argument("--json", action="store_true", help="the summary as json instead of the table")
    ap.add_argument("--csv", metavar="FILE", help="one row per block")
    ap.add_argument("--summary-append", metavar="FILE", help="one row per builder appended to a csv (one set per utc date)")
    ap.add_argument("--quiet", action="store_true", help="no table on stdout")
    ap.add_argument("--rpc", action="append", metavar="URL", help="json-rpc endpoint (repeatable, tried in order)")
    ap.add_argument("--workers", type=int, default=4, help="parallel requests (default 4)")
    ap.add_argument("--version", action="version", version=f"builderwatch {__version__}")
    args = ap.parse_args(argv)

    rpc = Rpc(args.rpc) if args.rpc else Rpc()
    try:
        head = rpc.block_number() - 1  # the newest block can still be reorganised or missing on a lagging endpoint
        if args.since:
            try:
                seconds = parse_since(args.since)
            except ValueError as exc:
                print(f"error: {exc}", file=sys.stderr)
                return 2
            first = first_block_since(rpc, head, int(rpc.header(head)["timestamp"], 16), seconds)
        else:
            if args.blocks < 1:
                print("error: --blocks must be at least 1", file=sys.stderr)
                return 2
            first = max(0, head - args.blocks + 1)
        blocks = scan(rpc, list(range(first, head + 1)), workers=max(1, args.workers))
    except (RpcError, RpcUnavailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not blocks:
        print("error: no blocks in the window", file=sys.stderr)
        return 2
    s = summary(blocks, group(blocks))
    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
            writer.writeheader()
            writer.writerows(csv_rows(blocks))
    if args.summary_append:
        append_summary(args.summary_append, summary_rows(s))
    if args.quiet:
        return 0
    print(json.dumps(s, indent=2) if args.json else table(s))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

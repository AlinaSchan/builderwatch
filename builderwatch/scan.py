"""fetch a window of headers, read the builder out of each, count the slots that got no block."""
from __future__ import annotations

import statistics
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from itertools import pairwise

from .builders import Named, name

SLOT = 12  # seconds; every block since the merge sits on a 12-second slot


@dataclass(frozen=True)
class Block:
    number: int
    time: int
    hash: str
    builder: Named
    recipient: str
    gas_used: int
    gas_limit: int
    base_fee: int  # wei
    blob_gas_used: int
    txs: int
    size: int

    @property
    def full(self) -> float:
        return self.gas_used / self.gas_limit if self.gas_limit else 0.0


def read_header(raw: dict) -> Block:
    """one header (eth_getBlockByNumber with hashes only) -> the block record."""
    return Block(
        number=int(raw["number"], 16), time=int(raw["timestamp"], 16), hash=raw["hash"], builder=name(raw.get("extraData") or "0x"),
        recipient=(raw.get("miner") or "").lower(), gas_used=int(raw["gasUsed"], 16), gas_limit=int(raw["gasLimit"], 16),
        base_fee=int(raw.get("baseFeePerGas") or "0x0", 16), blob_gas_used=int(raw.get("blobGasUsed") or "0x0", 16),
        txs=len(raw.get("transactions") or []), size=int(raw.get("size") or "0x0", 16),
    )


def scan(rpc, numbers: list[int], workers: int = 4, per_request: int = 25) -> list[Block]:
    """headers only: a block's header with its transaction hashes is about 20 kb, so a whole hour is a few megabytes."""
    chunks = [numbers[i:i + per_request] for i in range(0, len(numbers), per_request)]
    blocks: list[Block] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for part in pool.map(lambda chunk: [read_header(h) for h in rpc.headers(chunk, per_request=per_request)], chunks):
            blocks.extend(part)
    return blocks


def missed_slots(blocks: list[Block]) -> int:
    """slots between the first and the last block that got no block: every 12 seconds of gap beyond the one slot a block takes."""
    return sum((b.time - a.time) // SLOT - 1 for a, b in pairwise(blocks))


@dataclass
class Builder:
    name: str
    site: str
    kind: str
    blocks: int = 0
    gas_used: int = 0
    gas_limit: int = 0
    txs: int = 0
    blobs: int = 0
    base_fees: list[int] = field(default_factory=list)
    recipients: dict[str, int] = field(default_factory=dict)
    texts: dict[str, int] = field(default_factory=dict)

    @property
    def full(self) -> float:
        return self.gas_used / self.gas_limit if self.gas_limit else 0.0

    @property
    def recipient(self) -> str:
        """the fee recipient this builder used most; a builder pays itself, a local block pays the validator's vault."""
        return max(self.recipients.items(), key=lambda kv: kv[1])[0] if self.recipients else ""


def group(blocks: list[Block]) -> list[Builder]:
    """builders by blocks built, most first; the local blocks together under "no builder", the unknown texts each on their own line."""
    found: dict[str, Builder] = {}
    for b in blocks:
        n = b.builder
        key = n.name if n.kind == "builder" or n.kind == "unknown" else "no builder"
        row = found.setdefault(key, Builder(key, n.site if n.kind == "builder" else "", n.kind if n.kind != "empty" else "local"))
        row.blocks += 1
        row.gas_used += b.gas_used
        row.gas_limit += b.gas_limit
        row.txs += b.txs
        row.blobs += b.blob_gas_used // 131072
        row.base_fees.append(b.base_fee)
        row.recipients[b.recipient] = row.recipients.get(b.recipient, 0) + 1
        if n.kind != "builder":
            row.texts[n.site or n.text or "(empty)"] = row.texts.get(n.site or n.text or "(empty)", 0) + 1
    return sorted(found.values(), key=lambda r: (-r.blocks, r.kind != "builder", r.name))


def median_base_fee(blocks: list[Block]) -> int:
    return int(statistics.median(b.base_fee for b in blocks)) if blocks else 0


def header_time(rpc, number: int) -> int:
    return int(rpc.header(number)["timestamp"], 16)


def first_block_since(rpc, head: int, head_time: int, seconds: int) -> int:
    """the first block inside the last `seconds`, by bisecting header timestamps: slots are 12 s,
    but missed slots make any block count an estimate."""
    target = head_time - seconds
    hi = head
    lo = max(0, head - 2 * (seconds // SLOT) - 10)
    while lo > 0 and header_time(rpc, lo) >= target:  # not old enough yet: step back further
        lo = max(0, lo - (hi - lo))
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if header_time(rpc, mid) >= target:
            hi = mid
        else:
            lo = mid
    return hi

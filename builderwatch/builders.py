"""naming the builder of a block from the 32 bytes of extra data it signs.

a block builder writes its name into `extraData` (the field a miner once used); a validator that
builds its own block leaves whatever its execution client puts there: geth an rlp list with the
version, besu / nethermind / reth / erigon a version string, some nothing at all. the table below
maps the names seen on mainnet to a short name and the builder's site; anything else is shown as
the text it is, so a new builder shows up as itself rather than as a wrong guess."""
from __future__ import annotations

from dataclasses import dataclass

# (needle in the lower-cased extra data, short name, site, source). the first ten were seen in the
# 2,000 blocks from 25,980,626 to 25,982,625 on 2026-09-15; the block named is the first one of each,
# and the extra data as it was is in the comment. the last five are names that were common in 2023
# and 2024 and did not show up in that sample: they are matched, and the source says so.
KNOWN: tuple[tuple[str, str, str, str], ...] = (
    ("titan", "titan", "titanbuilder.xyz", "block 25,980,629, 2026-09-15"),  # Titan (titanbuilder.xyz)
    ("quasar", "quasar", "quasar.win", "block 25,980,627, 2026-09-15"),  # ✨ Quasar (quasar.win) ✨
    ("buildernet", "buildernet", "buildernet.org", "block 25,980,653, 2026-09-15"),  # BuilderNet
    ("eureka", "eureka", "eurekabuilder.xyz", "block 25,980,626, 2026-09-15"),  # Eureka (eurekabuilder.xyz)
    ("bombora", "bombora", "bombora.build", "block 25,980,644, 2026-09-15"),  # bombora.build 🌊
    ("bobthebuilder", "bob the builder", "bobthebuilder.xyz", "block 25,980,816, 2026-09-15"),  # bobTheBuilder.xyz
    ("btcs.com", "builder+", "btcs.com/builder", "block 25,981,030, 2026-09-15"),  # Builder+ www.btcs.com/builder
    ("bitget", "bitget", "bitget.com", "block 25,981,865, 2026-09-15"),  # Bitget(https://www.bitget.com/)
    ("ultrasound.money", "ultra sound", "builder.ultrasound.money", "block 25,981,102, 2026-09-15"),  # builder.ultrasound.money
    ("ethgas", "ethgas", "ethgas.com", "block 25,981,377, 2026-09-15"),  # ethgas-realtime-rpc
    ("beaverbuild", "beaverbuild", "beaverbuild.org", "not seen in the 2026-09-15 sample; the name it wrote in 2023-2024"),
    ("rsync", "rsync", "rsync-builder.xyz", "not seen in the 2026-09-15 sample; the name it wrote in 2023-2024"),
    ("illuminate dmocratize dstribute", "flashbots", "flashbots.net", "not seen in the 2026-09-15 sample; the name it wrote in 2023-2024"),
    ("penguinbuild", "penguin", "penguinbuild.org", "not seen in the 2026-09-15 sample; the name it wrote in 2024"),
    ("jetbldr", "jet", "jetbldr.xyz", "not seen in the 2026-09-15 sample; the name it wrote in 2024"),
)

CLIENTS = ("geth", "besu", "nethermind", "reth", "erigon", "ethereumjs", "nimbus", "lighthouse", "teku", "prysm", "lodestar", "grandine")


@dataclass(frozen=True)
class Named:
    name: str  # the short name of the builder, or "no builder" for a block a validator built itself
    site: str  # the builder's site, or the client that built the local block, or ""
    kind: str  # "builder", "local", "unknown", "empty"
    text: str  # what extraData said, printable


def _rlp_strings(raw: bytes) -> list[bytes] | None:
    """geth's default extra data is an rlp list [version, "geth", "go1.x", "linux"]; decode just enough of rlp
    to read that (a list of short strings and one small number)."""
    if not raw or raw[0] < 0xC0 or raw[0] > 0xF7:
        return None
    length = raw[0] - 0xC0
    if length != len(raw) - 1:
        return None
    body, items, i = raw[1:], [], 0
    while i < len(body):
        first = body[i]
        if first < 0x80:
            items.append(bytes([first]))
            i += 1
        elif first <= 0xB7:
            n = first - 0x80
            items.append(body[i + 1:i + 1 + n])
            i += 1 + n
        else:
            return None
    return items


def printable(raw: bytes) -> str:
    """the extra data as text: utf-8 where it is, with the bytes that are not shown as \\x.."""
    text = raw.decode("utf-8", errors="backslashreplace")
    return "".join(c if c.isprintable() else f"\\x{ord(c):02x}" if ord(c) < 256 else c for c in text)


def name(extra_hex: str) -> Named:
    raw = bytes.fromhex((extra_hex or "0x")[2:])
    if not raw:
        return Named("no builder", "", "empty", "")
    text = printable(raw)
    low = text.lower()
    for needle, short, site, _source in KNOWN:
        if needle in low:
            return Named(short, site, "builder", text)
    parts = _rlp_strings(raw)
    if parts and len(parts) == 4 and parts[1] == b"geth":
        version = int.from_bytes(parts[0], "big")
        return Named("no builder", f"geth {version >> 16}.{(version >> 8) & 0xFF}.{version & 0xFF}", "local", text)
    for client in CLIENTS:
        if low.startswith(client) or f"/{client}" in low or f" {client}" in low:
            return Named("no builder", text, "local", text)
    return Named(text[:40], "", "unknown", text)

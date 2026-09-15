"""talks to a public rpc. skipped unless BUILDERWATCH_LIVE=1."""
import os
from itertools import pairwise

import pytest

from builderwatch.rpc import Rpc
from builderwatch.scan import SLOT, group, missed_slots, scan

pytestmark = pytest.mark.skipif(os.environ.get("BUILDERWATCH_LIVE") != "1", reason="set BUILDERWATCH_LIVE=1")


def test_the_last_blocks_have_builders_the_table_knows():
    rpc = Rpc()
    head = rpc.block_number() - 1
    blocks = scan(rpc, list(range(head - 29, head + 1)), workers=2)
    assert [b.number for b in blocks] == list(range(head - 29, head + 1))
    kinds = [b.builder.kind for b in blocks]
    assert kinds.count("unknown") <= len(blocks) // 4, [b.builder.text for b in blocks if b.builder.kind == "unknown"]
    assert kinds.count("builder") >= len(blocks) // 2  # most blocks come through mev-boost
    for b in blocks:
        assert 0 < b.gas_used <= b.gas_limit and b.base_fee > 0 and len(b.recipient) == 42
    assert all(b.time - a.time >= SLOT and (b.time - a.time) % SLOT == 0 for a, b in pairwise(blocks))
    assert 0 <= missed_slots(blocks) <= 10
    rows = group(blocks)
    assert rows and rows[0].blocks >= 2 and sum(r.blocks for r in rows) == len(blocks)


def test_a_known_block_is_still_quasar():
    header = Rpc().header(25_982_578)
    assert header["extraData"] == "0xe29ca82051756173617220287175617361722e77696e2920e29ca8"
    assert header["miner"].lower() == "0x396343362be2a4da1ce0c1c210945346fb82aa49"

"""offline: naming from real extra data, the header record, missed slots, the grouping, the table, the csv and the daily file."""
import csv
import json

import pytest

from builderwatch import builders, cli
from builderwatch.builders import name, printable
from builderwatch.rpc import RpcUnavailable
from builderwatch.scan import first_block_since, group, missed_slots, scan

# extra data as it sits in mainnet headers
QUASAR = "0xe29ca82051756173617220287175617361722e77696e2920e29ca8"  # block 25,982,578: "✨ Quasar (quasar.win) ✨"
TITAN = "0x" + b"Titan (titanbuilder.xyz)".hex()
GETH = "0xd88301110384676574688867 6f312e32362e34856c696e7578".replace(" ", "")  # rlp [1.17.3, "geth", "go1.26.4", "linux"]
BESU = "0x" + b"besu 26.8.1".hex()
NETHERMIND = "0x" + b"Nethermind v1.37.2".hex()
RETH = "0x" + b"reth/v2.4.1/linux".hex()
BOMBORA = "0x" + "bombora.build 🌊".encode().hex()
DOT = "0x2e"


def test_names_from_real_extra_data():
    assert name(QUASAR).name == "quasar" and name(QUASAR).site == "quasar.win" and name(QUASAR).kind == "builder"
    assert name(QUASAR).text == "✨ Quasar (quasar.win) ✨"
    assert name(TITAN).name == "titan" and name(BOMBORA).name == "bombora"
    assert name("0x" + b"BuilderNet (Flashbots)".hex()).name == "buildernet"
    assert name("0x" + b"Builder+ btcs.com | ethgas.com".hex()).name == "builder+"


def test_local_blocks_are_named_by_their_client():
    geth = name(GETH)
    assert geth.name == "no builder" and geth.kind == "local" and geth.site == "geth 1.17.3"
    assert name(BESU).site == "besu 26.8.1" and name(NETHERMIND).site == "Nethermind v1.37.2" and name(RETH).site == "reth/v2.4.1/linux"
    assert name("0x").kind == "empty" and name("0x").name == "no builder"


def test_unknown_text_is_shown_as_itself():
    found = name(DOT)
    assert found.kind == "unknown" and found.name == "." and found.site == ""
    weird = name("0x" + b"new builder 3000".hex())
    assert weird.kind == "unknown" and weird.name == "new builder 3000"


def test_printable_keeps_utf8_and_escapes_the_rest():
    assert printable(b"Titan") == "Titan"
    assert printable(bytes.fromhex(GETH[2:])).endswith("linux")
    assert "\\x01" in printable(bytes.fromhex(GETH[2:]))


def test_every_known_line_has_a_source():
    for needle, short, site, source in builders.KNOWN:
        assert needle == needle.lower() and short and site and source.startswith(("block ", "not seen"))
    assert name("0x" + b"builder.ultrasound.money".hex()).name == "ultra sound"
    assert name("0x" + b"ethgas-realtime-rpc".hex()).name == "ethgas"


def header(number, ts, extra, miner="0x" + "aa" * 20, gas_used=30_000_000, gas_limit=60_000_000, base_fee=57_000_000,
           blob_gas=131072 * 3, txs=200):
    return {"number": hex(number), "timestamp": hex(ts), "hash": "0x" + f"{number:064x}", "extraData": extra, "miner": miner,
            "gasUsed": hex(gas_used), "gasLimit": hex(gas_limit), "baseFeePerGas": hex(base_fee), "blobGasUsed": hex(blob_gas),
            "transactions": ["0x" + "11" * 32] * txs, "size": hex(90_000)}


TITAN_PAYS = "0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97"
LIDO_VAULT = "0x388c818ca8b9251b393131c08a736a67ccb19297"


class FakeRpc:
    """twelve blocks: titan x6, quasar x3, two local (geth to the lido vault, besu), one empty extra data; one missed slot after block 4."""

    def __init__(self):
        t = self.t0 = 1_789_472_000
        self.by_number = {}
        specs = [(TITAN, TITAN_PAYS), (TITAN, TITAN_PAYS), (QUASAR, "0x396343362be2a4da1ce0c1c210945346fb82aa49"), (TITAN, TITAN_PAYS),
                 (GETH, LIDO_VAULT), (TITAN, TITAN_PAYS), (QUASAR, "0x396343362be2a4da1ce0c1c210945346fb82aa49"), (BESU, "0x" + "bb" * 20),
                 (TITAN, TITAN_PAYS), ("0x", "0x" + "cc" * 20), (QUASAR, "0x396343362be2a4da1ce0c1c210945346fb82aa49"), (TITAN, TITAN_PAYS)]
        for i, (extra, miner) in enumerate(specs):
            number = 100 + i
            stamp = t + 12 * i + (12 if i >= 5 else 0)  # one slot missed between 104 and 105
            self.by_number[number] = header(number, stamp, extra, miner, gas_used=20_000_000 + 2_000_000 * i)
        self.batches = []

    def block_number(self):
        return 112

    def header(self, number="latest"):
        number = 112 if number == "latest" else number
        if number not in self.by_number:  # older than the window: a plain block every 12 s, for the bisection
            return header(number, self.t0 - 12 * (100 - number), TITAN, TITAN_PAYS)
        return self.by_number[number]

    def headers(self, numbers, per_request=25):
        self.batches.append(list(numbers))
        return [self.by_number[n] for n in numbers]


def test_read_header_and_missed_slots():
    rpc = FakeRpc()
    blocks = scan(rpc, list(range(100, 112)), workers=2, per_request=5)
    assert [b.number for b in blocks] == list(range(100, 112)) and len(rpc.batches) == 3
    assert blocks[0].builder.name == "titan" and blocks[0].recipient == TITAN_PAYS and blocks[0].full == pytest.approx(1 / 3)
    assert blocks[4].builder.kind == "local" and blocks[9].builder.kind == "empty"
    assert missed_slots(blocks) == 1 and blocks[0].txs == 200 and blocks[0].blob_gas_used == 131072 * 3


def test_group_and_summary():
    blocks = scan(FakeRpc(), list(range(100, 112)))
    rows = group(blocks)
    assert [(r.name, r.blocks) for r in rows] == [("titan", 6), ("quasar", 3), ("no builder", 3)]
    local = rows[2]
    assert local.kind == "local" and sorted(local.texts) == ["(empty)", "besu 26.8.1", "geth 1.17.3"] and len(local.recipients) == 3
    assert rows[0].recipient == TITAN_PAYS
    s = cli.summary(blocks, rows)
    assert s["slots"] == 13 and s["slots_missed"] == 1 and s["blocks"] == 12 and s["builders"][0]["share"] == 0.5
    assert s["blobs"] == 36 and s["txs"] == 2400 and s["gas_limit"] == 60_000_000


def test_cli_table_json_csv_and_daily_file(monkeypatch, capsys, tmp_path):
    monkeypatch.setattr(cli, "Rpc", lambda urls=None: FakeRpc())
    per_block, daily = tmp_path / "blocks.csv", tmp_path / "daily.csv"
    assert cli.main(["--blocks", "12", "--csv", str(per_block), "--summary-append", str(daily)]) == 0
    out = capsys.readouterr().out
    assert "who built the last 12 blocks: 100 to 111" in out
    assert out.splitlines()[3].startswith("titan") and "50.0%" in out.splitlines()[3] and "titanbuilder.xyz" in out.splitlines()[3]
    assert "no builder" in out and "validators' own nodes" in out and "slots without a block: 1 of 13" in out
    with open(per_block, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 12 and rows[2]["builder"] == "quasar" and rows[4]["kind"] == "local"
    assert rows[2]["extra_data"] == "✨ Quasar (quasar.win) ✨"
    assert cli.main(["--blocks", "12", "--summary-append", str(daily), "--quiet"]) == 0  # the same day again: replaced, not doubled
    with open(daily, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    assert [(r["builder"], r["blocks_built"], r["slots_missed"]) for r in rows] == [("titan", "6", "1"), ("quasar", "3", "1"),
                                                                                      ("no builder", "3", "1")]
    assert rows[0]["share"] == "0.5000" and rows[0]["fee_recipient"] == TITAN_PAYS
    assert cli.main(["--blocks", "12", "--json"]) == 0
    doc = json.loads(capsys.readouterr().out)
    assert doc["to_block"] == 111 and doc["builders"][1]["name"] == "quasar" and doc["slots_missed_share"] == pytest.approx(1 / 13)


def test_cli_since_and_errors(monkeypatch, capsys):
    monkeypatch.setattr(cli, "Rpc", lambda urls=None: FakeRpc())
    assert cli.main(["--since", "1m"]) == 0  # 60 s back from block 111: blocks 106..111
    assert "who built the last 6 blocks: 106 to 111" in capsys.readouterr().out
    assert cli.main(["--since", "soon"]) == 2 and cli.main(["--blocks", "0"]) == 2
    assert cli.parse_since("2h") == 7200 and cli.parse_since("1d") == 86400

    class Down(FakeRpc):
        def block_number(self):
            raise RpcUnavailable("all down")

    monkeypatch.setattr(cli, "Rpc", lambda urls=None: Down())
    assert cli.main([]) == 2 and "all down" in capsys.readouterr().err


def test_first_block_since_bisects_timestamps():
    rpc = FakeRpc()
    now = int(rpc.header(111)["timestamp"], 16)
    assert first_block_since(rpc, 111, now, 60) == 106
    assert first_block_since(rpc, 111, now, 12 * 11 + 12) == 100  # the missed slot makes 12 blocks span 13 slots


def test_formatting():
    assert cli.short("0x4838b106fce9647bdf1e7877bf73ce8b0bad5f97") == "0x4838…5f97"
    assert cli.gwei(57_000_000) == "0.057" and cli.gwei(1234) == "1.234e-06"

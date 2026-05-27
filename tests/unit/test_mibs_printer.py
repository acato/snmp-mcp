# Copyright 2026 snmp-mcp contributors
# Licensed under the Apache License, Version 2.0 (see LICENSE)
"""Unit tests for mibs/printer.py — PRINTER-MIB."""

from __future__ import annotations

import pytest

from snmp_mcp import transport
from snmp_mcp.errors import SnmpUnsupported
from snmp_mcp.mibs.printer import printer_status


async def test_printer_status_happy_path(monkeypatch, fake_session) -> None:
    # Probe returns idle (3).
    probe_resp = [("1.3.6.1.2.1.43.5.1.1.2.1.1", 3, "Integer")]

    supplies_rows = [
        # Supply 1.1: Black Toner — type=3 (toner), unit=19 (percent), max=100, lvl=65
        ("1.3.6.1.2.1.43.11.1.1.1.1.1", 1, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.5.1.1", 3, "Integer"),  # type=toner
        ("1.3.6.1.2.1.43.11.1.1.6.1.1", "Black Toner", "OctetString"),
        ("1.3.6.1.2.1.43.11.1.1.7.1.1", 19, "Integer"),  # unit=percent
        ("1.3.6.1.2.1.43.11.1.1.8.1.1", 100, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.9.1.1", 65, "Integer"),
        # Supply 1.2: drum (opc=9), level -3 (known but unmeasured) — preserved
        ("1.3.6.1.2.1.43.11.1.1.1.1.2", 2, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.5.1.2", 9, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.6.1.2", "Drum", "OctetString"),
        ("1.3.6.1.2.1.43.11.1.1.7.1.2", 19, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.8.1.2", 100, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.9.1.2", -3, "Integer"),
        # Supply 1.3: ink (5), level -2 (unknown) — normalized to None
        ("1.3.6.1.2.1.43.11.1.1.1.1.3", 3, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.5.1.3", 5, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.6.1.3", "Cyan Ink", "OctetString"),
        ("1.3.6.1.2.1.43.11.1.1.7.1.3", 19, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.8.1.3", 100, "Integer"),
        ("1.3.6.1.2.1.43.11.1.1.9.1.3", -2, "Integer"),
    ]

    input_rows = [
        ("1.3.6.1.2.1.43.8.2.1.13.1.1", "Tray 1", "OctetString"),
        ("1.3.6.1.2.1.43.8.2.1.9.1.1", 250, "Integer"),
        ("1.3.6.1.2.1.43.8.2.1.10.1.1", 200, "Integer"),
        ("1.3.6.1.2.1.43.8.2.1.11.1.1", 0, "Integer"),
    ]

    output_rows = [
        ("1.3.6.1.2.1.43.9.2.1.13.1.1", "Top", "OctetString"),
        ("1.3.6.1.2.1.43.9.2.1.5.1.1", 100, "Integer"),
        ("1.3.6.1.2.1.43.9.2.1.6.1.1", 0, "Integer"),
        ("1.3.6.1.2.1.43.9.2.1.7.1.1", 0, "Integer"),
    ]

    alert_rows = [
        ("1.3.6.1.2.1.43.18.1.1.2.1.1", 4, "Integer"),  # severity=warning
        ("1.3.6.1.2.1.43.18.1.1.3.1.1", 3, "Integer"),  # training=untrained
        ("1.3.6.1.2.1.43.18.1.1.4.1.1", 11, "Integer"),  # group=markerSupplies
        ("1.3.6.1.2.1.43.18.1.1.7.1.1", 1101, "Integer"),
        ("1.3.6.1.2.1.43.18.1.1.8.1.1", "Black Toner low", "OctetString"),
    ]

    state = {
        "1.3.6.1.2.1.43.11.1": iter(supplies_rows),
        "1.3.6.1.2.1.43.8.2": iter(input_rows),
        "1.3.6.1.2.1.43.9.2": iter(output_rows),
        "1.3.6.1.2.1.43.18.1": iter(alert_rows),
    }

    async def fake_get(_session, _oids):
        return list(probe_resp)

    async def fake_bulk(_session, oid, _max):
        for prefix, it in state.items():
            if oid.startswith(prefix):
                try:
                    return [next(it)]
                except StopIteration:
                    return [(prefix + ".999", None, "endOfMibView")]
        return [("9.9.9", None, "endOfMibView")]

    monkeypatch.setattr(transport, "_perform_get", fake_get)
    monkeypatch.setattr(transport, "_perform_bulk", fake_bulk)

    result = await printer_status(fake_session)
    d = result["data"]
    assert d["printer_status"] == "idle"
    assert len(d["supplies"]) == 3
    by_descr = {s["descr"]: s for s in d["supplies"]}
    assert by_descr["Black Toner"]["type"] == "toner"
    assert by_descr["Black Toner"]["current_level"] == 65
    assert by_descr["Black Toner"]["level_pct"] == 65.0
    # -3 sentinel preserved.
    assert by_descr["Drum"]["current_level"] == -3
    assert by_descr["Drum"]["level_pct"] is None
    # -2 sentinel normalized to None.
    assert by_descr["Cyan Ink"]["current_level"] is None
    assert by_descr["Cyan Ink"]["level_pct"] is None
    # Trays.
    assert d["input_trays"][0]["name"] == "Tray 1"
    assert d["input_trays"][0]["capacity"] == 250
    # Output bins.
    assert d["output_bins"][0]["name"] == "Top"
    # Alerts.
    assert d["alerts"][0]["severity"] == "warning"
    assert d["alerts"][0]["group"] == "markerSupplies"
    assert d["alerts"][0]["description"] == "Black Toner low"


async def test_printer_status_unsupported(monkeypatch, fake_session) -> None:
    async def fake_get(_session, _oids):
        return [("1.3.6.1.2.1.43.5.1.1.2.1.1", None, "noSuchInstance")]

    monkeypatch.setattr(transport, "_perform_get", fake_get)
    with pytest.raises(SnmpUnsupported):
        await printer_status(fake_session)

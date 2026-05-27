# Copyright 2026 snmp-mcp contributors
# Licensed under the Apache License, Version 2.0 (see LICENSE)
"""Unit tests for mibs/detect.py — device_detect probe."""

from __future__ import annotations

from snmp_mcp import transport
from snmp_mcp.mibs.detect import device_detect


async def test_detect_mikrotik_router(monkeypatch, fake_session) -> None:
    async def fake_get(_session, _oids):
        return [
            ("1.3.6.1.2.1.1.2.0", "1.3.6.1.4.1.14988.1", "ObjectIdentifier"),
            ("1.3.6.1.2.1.1.1.0", "RouterOS CRS312-4C+8XG", "OctetString"),
            ("1.3.6.1.2.1.2.1.0", 15, "Integer"),
            ("1.3.6.1.2.1.25.1.1.0", 1234567, "TimeTicks"),
            # Printer MIB not implemented on a switch.
            ("1.3.6.1.2.1.43.5.1.1.2.1.1", None, "noSuchInstance"),
        ]

    monkeypatch.setattr(transport, "_perform_get", fake_get)
    result = await device_detect(fake_session)
    d = result["data"]
    assert d["vendor_hint"] == "MikroTik"
    assert "SNMPv2-MIB" in d["supported_mibs"]
    assert "IF-MIB" in d["supported_mibs"]
    assert "HOST-RESOURCES-MIB" in d["supported_mibs"]
    assert "PRINTER-MIB" not in d["supported_mibs"]


async def test_detect_epson_printer(monkeypatch, fake_session) -> None:
    async def fake_get(_session, _oids):
        return [
            ("1.3.6.1.2.1.1.2.0", "1.3.6.1.4.1.1248.1.2.2", "ObjectIdentifier"),
            ("1.3.6.1.2.1.1.1.0", "EPSON Built-in 11.42", "OctetString"),
            ("1.3.6.1.2.1.2.1.0", 2, "Integer"),
            ("1.3.6.1.2.1.25.1.1.0", 1234567, "TimeTicks"),
            ("1.3.6.1.2.1.43.5.1.1.2.1.1", 3, "Integer"),
        ]

    monkeypatch.setattr(transport, "_perform_get", fake_get)
    result = await device_detect(fake_session)
    d = result["data"]
    assert d["vendor_hint"] == "Seiko Epson"
    assert d["supported_mibs"] == ["SNMPv2-MIB", "IF-MIB", "HOST-RESOURCES-MIB", "PRINTER-MIB"]


async def test_detect_bare_switch_no_host_resources(monkeypatch, fake_session) -> None:
    async def fake_get(_session, _oids):
        return [
            ("1.3.6.1.2.1.1.2.0", "1.3.6.1.4.1.9.1.123", "ObjectIdentifier"),
            ("1.3.6.1.2.1.1.1.0", "Cisco IOS", "OctetString"),
            ("1.3.6.1.2.1.2.1.0", 48, "Integer"),
            # HOST-RESOURCES not implemented on a bare switch.
            ("1.3.6.1.2.1.25.1.1.0", None, "noSuchInstance"),
            ("1.3.6.1.2.1.43.5.1.1.2.1.1", None, "noSuchInstance"),
        ]

    monkeypatch.setattr(transport, "_perform_get", fake_get)
    result = await device_detect(fake_session)
    d = result["data"]
    assert d["vendor_hint"] == "Cisco"
    assert "HOST-RESOURCES-MIB" not in d["supported_mibs"]
    assert "PRINTER-MIB" not in d["supported_mibs"]

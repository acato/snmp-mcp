# Copyright 2026 snmp-mcp contributors
# Licensed under the Apache License, Version 2.0 (see LICENSE)
"""Live integration tests.

Gated on the ``SNMP_MCP_LIVE_HOST`` env var (auto-skipped via
``conftest.py.pytest_collection_modifyitems`` if unset). These tests run
against a real SNMP agent and exercise all 9 tools READ-ONLY. No SET
operations of any kind.

Required env vars when running:
  - ``SNMP_MCP_LIVE_HOST``         — host alias (and the conf section name)
  - ``SNMP_MCP_LIVE_ADDRESS``      — actual IP/hostname of the target
  - ``SNMP_MCP_LIVE_VERSION``      — v1 / v2c / v3 (default v2c)
  - ``SNMP_MCP_LIVE_COMMUNITY``    — for v1/v2c
  - ``SNMP_MCP_LIVE_USER``         — for v3
  - ``SNMP_MCP_LIVE_AUTH_PROTO``   — for v3
  - ``SNMP_MCP_LIVE_AUTH_PASS``    — for v3
  - ``SNMP_MCP_LIVE_PRIV_PROTO``   — for v3 (optional)
  - ``SNMP_MCP_LIVE_PRIV_PASS``    — for v3 (optional)

Optional env var:
  - ``SNMP_MCP_LIVE_PRINTER_HOST`` — separate host alias for the printer
    integration test; if unset, printer test is skipped.
"""

from __future__ import annotations

import os

import pytest

from snmp_mcp.config import HostConfig
from snmp_mcp.mibs.detect import device_detect
from snmp_mcp.mibs.host_resources import host_resources
from snmp_mcp.mibs.interfaces import interfaces_list
from snmp_mcp.mibs.printer import printer_status
from snmp_mcp.mibs.system import system_info
from snmp_mcp.session import SessionCache
from snmp_mcp.transport import snmp_bulk_walk, snmp_get, snmp_table, snmp_walk

pytestmark = pytest.mark.asyncio


def _live_host_cfg() -> HostConfig:
    """Build a HostConfig from SNMP_MCP_LIVE_* env vars."""
    name = os.environ["SNMP_MCP_LIVE_HOST"]
    return HostConfig(
        name=name,
        address=os.environ.get("SNMP_MCP_LIVE_ADDRESS", name),
        version=os.environ.get("SNMP_MCP_LIVE_VERSION", "v2c"),
        community=os.environ.get("SNMP_MCP_LIVE_COMMUNITY"),
        user=os.environ.get("SNMP_MCP_LIVE_USER"),
        auth_proto=os.environ.get("SNMP_MCP_LIVE_AUTH_PROTO"),
        auth_pass=os.environ.get("SNMP_MCP_LIVE_AUTH_PASS"),
        priv_proto=os.environ.get("SNMP_MCP_LIVE_PRIV_PROTO"),
        priv_pass=os.environ.get("SNMP_MCP_LIVE_PRIV_PASS"),
        timeout=float(os.environ.get("SNMP_MCP_LIVE_TIMEOUT", "3.0")),
        retries=int(os.environ.get("SNMP_MCP_LIVE_RETRIES", "2")),
    )


def _live_printer_cfg() -> HostConfig | None:
    name = os.environ.get("SNMP_MCP_LIVE_PRINTER_HOST")
    if not name:
        return None
    return HostConfig(
        name=name,
        address=os.environ.get("SNMP_MCP_LIVE_PRINTER_ADDRESS", name),
        version=os.environ.get("SNMP_MCP_LIVE_PRINTER_VERSION", "v2c"),
        community=os.environ.get("SNMP_MCP_LIVE_PRINTER_COMMUNITY", "public"),
        timeout=float(os.environ.get("SNMP_MCP_LIVE_PRINTER_TIMEOUT", "3.0")),
        retries=int(os.environ.get("SNMP_MCP_LIVE_PRINTER_RETRIES", "2")),
    )


@pytest.fixture(scope="module")
def live_session():
    cfg = _live_host_cfg()
    cfg.validate()
    cache = SessionCache()
    return cache.get(cfg)


@pytest.fixture(scope="module")
def live_printer_session():
    cfg = _live_printer_cfg()
    if cfg is None:
        pytest.skip("SNMP_MCP_LIVE_PRINTER_HOST not set")
    cfg.validate()
    cache = SessionCache()
    return cache.get(cfg)


# --- Generic primitives ------------------------------------------------------


async def test_live_get_sys_name(live_session) -> None:
    """A single GET against sysName.0."""
    result = await snmp_get(live_session, ["1.3.6.1.2.1.1.5.0"])
    vb = result["varbinds"]["1.3.6.1.2.1.1.5.0"]
    assert vb["value"] is not None


async def test_live_walk_system_group(live_session) -> None:
    """Walk the SNMPv2-MIB::system subtree — always present on a conformant agent."""
    result = await snmp_walk(live_session, "1.3.6.1.2.1.1")
    assert len(result["rows"]) >= 5  # sysDescr through sysServices = 7 leaves


async def test_live_bulk_walk_system_group(live_session) -> None:
    result = await snmp_bulk_walk(live_session, "1.3.6.1.2.1.1")
    assert len(result["rows"]) >= 5


async def test_live_table_iftable(live_session) -> None:
    from snmp_mcp import oids

    result = await snmp_table(
        live_session,
        oids.IF_TABLE,
        column_names=oids.IF_TABLE_COLUMNS,
    )
    assert result["rows"], "expected at least one ifTable row"


# --- MIB wrappers ------------------------------------------------------------


async def test_live_system_info(live_session) -> None:
    result = await system_info(live_session)
    d = result["data"]
    assert d["sysName"] is not None
    assert d["sysObjectID"] is not None
    assert isinstance(d["sysUpTime"], int) and d["sysUpTime"] > 0


async def test_live_interfaces_list(live_session) -> None:
    result = await interfaces_list(live_session)
    assert result["data"], "expected at least one interface"
    # On a 10G switch we expect the ifHighSpeed fallback to kick in on at
    # least one interface.
    if_speed_sources = {row["ifSpeed_source"] for row in result["data"]}
    assert "ifSpeed" in if_speed_sources or "ifHighSpeed" in if_speed_sources


async def test_live_host_resources(live_session) -> None:
    """Some agents don't implement HOST-RESOURCES-MIB; tolerate that."""
    from snmp_mcp.errors import SnmpUnsupported

    try:
        result = await host_resources(live_session)
    except SnmpUnsupported:
        pytest.skip("agent does not implement HOST-RESOURCES-MIB")
    assert result["data"]["hrSystemUptime_centiseconds"] is not None


async def test_live_device_detect(live_session) -> None:
    result = await device_detect(live_session)
    d = result["data"]
    assert d["sys_object_id"] is not None
    assert "SNMPv2-MIB" in d["supported_mibs"]


async def test_live_printer_status(live_printer_session) -> None:
    result = await printer_status(live_printer_session)
    # Even an idle printer reports a status enum.
    assert result["data"]["printer_status"] is not None

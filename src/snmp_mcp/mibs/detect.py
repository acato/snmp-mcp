# Copyright 2026 snmp-mcp contributors
# Licensed under the Apache License, Version 2.0 (see LICENSE)
"""``device_detect`` — heuristic probe of which standard MIBs a device speaks.

Issues a small, fixed set of GETs (no walks, no tables) and reports which
of the IETF MIBs we care about answered. Useful as a smoke-test before
calling any of the heavier wrappers.
"""

from __future__ import annotations

from typing import Any

from .. import oids
from ..session import HostSession
from ..transport import snmp_get


async def device_detect(session: HostSession) -> dict[str, Any]:
    """Probe sysObjectID + one OID per supported MIB; report what answered."""
    probe = [
        oids.SYS_OBJECT_ID,
        oids.SYS_DESCR,
        oids.IF_NUMBER,
        oids.HR_SYSTEM_UPTIME,
        oids.PRT_GENERAL_PRINTER_STATUS + ".1.1",
    ]
    result = await snmp_get(session, probe)
    vb = result["varbinds"]

    sys_object_id = _str_or_none(vb.get(oids.SYS_OBJECT_ID, {}).get("value"))
    sys_descr = _str_or_none(vb.get(oids.SYS_DESCR, {}).get("value"))

    supported = []
    # SNMPv2-MIB is implied by any successful response to sysObjectID / sysDescr.
    if sys_object_id is not None or sys_descr is not None:
        supported.append("SNMPv2-MIB")
    if _is_present(vb.get(oids.IF_NUMBER, {})):
        supported.append("IF-MIB")
    if _is_present(vb.get(oids.HR_SYSTEM_UPTIME, {})):
        supported.append("HOST-RESOURCES-MIB")
    if _is_present(vb.get(oids.PRT_GENERAL_PRINTER_STATUS + ".1.1", {})):
        supported.append("PRINTER-MIB")

    vendor_hint = oids.vendor_from_sys_object_id(sys_object_id) if sys_object_id else "unknown"

    return {
        "data": {
            "sys_object_id": sys_object_id,
            "sys_descr": sys_descr,
            "vendor_hint": vendor_hint,
            "supported_mibs": supported,
        },
        "warnings": result["warnings"],
    }


def _is_present(vb_entry: dict[str, Any]) -> bool:
    """Return True if a varbind entry holds a real (non-sentinel) value."""
    if not vb_entry:
        return False
    if vb_entry.get("value") is None:
        return False
    type_name = vb_entry.get("type", "")
    return type_name not in ("noSuchInstance", "noSuchObject", "endOfMibView")


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)

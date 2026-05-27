# Copyright 2026 snmp-mcp contributors
# Licensed under the Apache License, Version 2.0 (see LICENSE)
"""``PRINTER-MIB`` → ``printer_status`` tool (RFC 3805).

Vendor-neutral: works for HP, Brother, Canon, OKI, Epson, Lexmark — the
standardized data model is what makes it possible.

Sentinel values defined by RFC 3805 §4.5:
  - ``-2`` ("unknown"): we return ``current_level=None`` so callers know.
  - ``-3`` ("known but unmeasurable"): we preserve as ``-3`` so callers can
    distinguish "we tried" from "no data at all".
"""

from __future__ import annotations

from typing import Any

from .. import oids
from ..errors import SnmpUnsupported
from ..session import HostSession
from ..transport import snmp_get, snmp_table

# RFC 3805 sentinel values for prtMarkerSuppliesLevel.
_LEVEL_UNKNOWN = -2
_LEVEL_NOT_MEASURED = -3


async def printer_status(session: HostSession) -> dict[str, Any]:
    """Return supplies + trays + bins + alerts for a printer.

    Raises ``SnmpUnsupported`` if the agent does not implement PRINTER-MIB.
    """
    # Probe with a small GET first; many printers expose
    # prtGeneralPrinterStatus.1.1 as the first conformant row.
    probe = await snmp_get(session, [oids.PRT_GENERAL_PRINTER_STATUS + ".1.1"])
    probe_vb = probe["varbinds"]
    probe_value = next(iter(probe_vb.values()), {}).get("value")
    probe_type = next(iter(probe_vb.values()), {}).get("type", "")
    if probe_value is None and probe_type in ("noSuchInstance", "noSuchObject"):
        raise SnmpUnsupported(
            "agent does not implement PRINTER-MIB (prtGeneralPrinterStatus missing)",
            host=session.host_cfg.name,
        )

    printer_status_int = _int_or_none(probe_value)
    printer_status_name = oids.PRT_GENERAL_STATUS_NAMES.get(
        printer_status_int,
        str(printer_status_int) if printer_status_int is not None else None,
    )

    # Supplies (toner / ink / drum / ...) — prtMarkerSuppliesTable.
    supplies_table = await snmp_table(
        session,
        oids.PRT_MARKER_SUPPLIES_TABLE,
        column_names=oids.PRT_MARKER_SUPPLIES_COLUMNS,
        use_bulk=True,
    )
    supplies = []
    for row in supplies_table["rows"]:
        type_enum = _int_or_none(row.get("prtMarkerSuppliesType"))
        unit_enum = _int_or_none(row.get("prtMarkerSuppliesSupplyUnit"))
        max_cap = _int_or_none(row.get("prtMarkerSuppliesMaxCapacity"))
        level_raw = _int_or_none(row.get("prtMarkerSuppliesLevel"))
        level: int | None = None if level_raw == _LEVEL_UNKNOWN else level_raw
        level_pct: float | None = None
        if level is not None and level >= 0 and max_cap is not None and max_cap > 0:
            level_pct = round((level / max_cap) * 100.0, 1)
        supplies.append(
            {
                "index": row["index"],
                "descr": _str_or_none(row.get("prtMarkerSuppliesDescription")),
                "type": oids.PRT_SUPPLY_TYPE_NAMES.get(
                    type_enum,
                    str(type_enum) if type_enum is not None else None,
                ),
                "type_enum": type_enum,
                "unit": oids.PRT_SUPPLY_UNIT_NAMES.get(
                    unit_enum,
                    str(unit_enum) if unit_enum is not None else None,
                ),
                "max_capacity": max_cap,
                "current_level": level,
                "level_pct": level_pct,
            }
        )

    # Input trays.
    input_table = await snmp_table(
        session,
        oids.PRT_INPUT_TABLE,
        column_names=oids.PRT_INPUT_COLUMNS,
        use_bulk=True,
    )
    input_trays = [
        {
            "index": row["index"],
            "name": _str_or_none(row.get("prtInputName")),
            "media_type": _str_or_none(row.get("prtInputMediaType")),
            "media_name": _str_or_none(row.get("prtInputMediaName")),
            "capacity": _int_or_none(row.get("prtInputMaxCapacity")),
            "current_level": _int_or_none(row.get("prtInputCurrentLevel")),
            "status": _int_or_none(row.get("prtInputStatus")),
        }
        for row in input_table["rows"]
    ]

    # Output bins.
    output_table = await snmp_table(
        session,
        oids.PRT_OUTPUT_TABLE,
        column_names=oids.PRT_OUTPUT_COLUMNS,
        use_bulk=True,
    )
    output_bins = [
        {
            "index": row["index"],
            "name": _str_or_none(row.get("prtOutputName")),
            "capacity": _int_or_none(row.get("prtOutputMaxCapacity")),
            "remaining_capacity": _int_or_none(row.get("prtOutputRemainingCapacity")),
            "status": _int_or_none(row.get("prtOutputStatus")),
        }
        for row in output_table["rows"]
    ]

    # Active alerts (printer panel alarms).
    alert_table = await snmp_table(
        session,
        oids.PRT_ALERT_TABLE,
        column_names=oids.PRT_ALERT_COLUMNS,
        use_bulk=True,
    )
    alerts = []
    for row in alert_table["rows"]:
        sev_enum = _int_or_none(row.get("prtAlertSeverityLevel"))
        train_enum = _int_or_none(row.get("prtAlertTrainingLevel"))
        group_enum = _int_or_none(row.get("prtAlertGroup"))
        alerts.append(
            {
                "index": row["index"],
                "severity": oids.PRT_ALERT_SEVERITY_NAMES.get(
                    sev_enum,
                    str(sev_enum) if sev_enum is not None else None,
                ),
                "training_level": oids.PRT_ALERT_TRAINING_NAMES.get(
                    train_enum,
                    str(train_enum) if train_enum is not None else None,
                ),
                "group": oids.PRT_ALERT_GROUP_NAMES.get(
                    group_enum,
                    str(group_enum) if group_enum is not None else None,
                ),
                "code": _int_or_none(row.get("prtAlertCode")),
                "description": _str_or_none(row.get("prtAlertDescription")),
                "location": _int_or_none(row.get("prtAlertLocation")),
            }
        )

    return {
        "data": {
            "printer_status": printer_status_name,
            "device_status": None,  # Filled below from hrDeviceStatus when available.
            "supplies": supplies,
            "input_trays": input_trays,
            "output_bins": output_bins,
            "alerts": alerts,
        },
        "warnings": (
            list(probe["warnings"])
            + list(supplies_table["warnings"])
            + list(input_table["warnings"])
            + list(output_table["warnings"])
            + list(alert_table["warnings"])
        ),
    }


def _int_or_none(v: Any) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _str_or_none(v: Any) -> str | None:
    if v is None:
        return None
    return str(v)

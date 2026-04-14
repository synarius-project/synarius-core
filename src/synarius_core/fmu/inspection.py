"""Parse FMI 2.0 ``modelDescription.xml`` inside a ``.fmu`` archive (ZIP)."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


class FmuInspectError(RuntimeError):
    """Failed to read or parse an FMU archive."""


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _scalar_type_and_dt(child: ET.Element | None) -> tuple[str, str]:
    if child is None:
        return "unknown", "float"
    ln = _local_name(child.tag)
    if ln == "Real":
        return "real", "float"
    if ln == "Integer":
        return "integer", "int"
    if ln == "Boolean":
        return "boolean", "bool"
    if ln == "String":
        return "string", "string"
    return ln.lower(), "float"


def _read_model_description_xml(z: zipfile.ZipFile) -> bytes:
    names = z.namelist()
    for n in names:
        if n.endswith("modelDescription.xml") and "/documentation/" not in n.replace("\\", "/"):
            return z.read(n)
    for n in names:
        if n.endswith("modelDescription.xml"):
            return z.read(n)
    raise FmuInspectError("No modelDescription.xml found in FMU archive.")


def inspect_fmu_bytes(archive_bytes: bytes) -> dict[str, Any]:
    """Parse FMI 2.0 model description from raw ``.fmu`` (ZIP) bytes."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive_bytes), "r") as z:
            xml_bytes = _read_model_description_xml(z)
    except zipfile.BadZipFile as exc:
        raise FmuInspectError("File is not a valid ZIP/FMU archive.") from exc
    return parse_model_description_xml(xml_bytes)


def inspect_fmu_path(path: str | Path) -> dict[str, Any]:
    """Load ``path`` (.fmu ZIP) and return structured inspection dict (JSON-serializable)."""
    p = Path(path).expanduser()
    if not p.is_file():
        raise FmuInspectError(f"FMU path is not a file: {p}")
    try:
        with zipfile.ZipFile(p, "r") as z:
            xml_bytes = _read_model_description_xml(z)
    except zipfile.BadZipFile as exc:
        raise FmuInspectError("File is not a valid ZIP/FMU archive.") from exc
    data = parse_model_description_xml(xml_bytes)
    data["path"] = str(p.resolve())
    return data


def _parse_md_root_attribs(att: dict[str, str]) -> tuple[str, str, str, str, str, str, str, str]:
    fmi_version = str(att.get("fmiVersion", "") or "")
    guid = str(att.get("guid", "") or "")
    model_identifier = str(att.get("modelName", "") or "")
    description = str(att.get("description", "") or "")
    author = str(att.get("author", "") or "")
    model_version = str(att.get("version", "") or "")
    generation_tool = str(att.get("generationTool", "") or "")
    generation_date = str(att.get("generationDateAndTime", "") or "")
    return (
        fmi_version,
        guid,
        model_identifier,
        description,
        author,
        model_version,
        generation_tool,
        generation_date,
    )


def _infer_fmu_type(root: ET.Element) -> str:
    fmu_type = "CoSimulation"
    for child in root:
        ln = _local_name(child.tag)
        if ln == "CoSimulation":
            fmu_type = "CoSimulation"
            break
        if ln == "ModelExchange":
            fmu_type = "ModelExchange"
    return fmu_type


def _parse_default_experiment_times(root: ET.Element) -> tuple[float | None, float | None, float | None]:
    step_size_hint: float | None = None
    start_time: float | None = None
    stop_time: float | None = None
    for child in root:
        if _local_name(child.tag) != "DefaultExperiment":
            continue
        ea = child.attrib
        if "stepSize" in ea:
            try:
                step_size_hint = float(ea["stepSize"])
            except (TypeError, ValueError):
                pass
        if "startTime" in ea:
            try:
                start_time = float(ea["startTime"])
            except (TypeError, ValueError):
                pass
        if "stopTime" in ea:
            try:
                stop_time = float(ea["stopTime"])
            except (TypeError, ValueError):
                pass
        break
    return step_size_hint, start_time, stop_time


def _scalar_variable_row(el: ET.Element) -> dict[str, Any] | None:
    ea = el.attrib
    name = str(ea.get("name", "") or "").strip()
    if not name:
        return None
    vr_raw = ea.get("valueReference")
    try:
        value_reference = int(vr_raw, 0) if isinstance(vr_raw, str) and vr_raw.startswith(("0x", "0X")) else int(vr_raw)
    except (TypeError, ValueError):
        value_reference = vr_raw
    causality = str(ea.get("causality", "") or "").strip().lower()
    variability = str(ea.get("variability", "") or "").strip().lower()
    type_child: ET.Element | None = None
    for ch in el:
        lnc = _local_name(ch.tag)
        if lnc in ("Real", "Integer", "Boolean", "String"):
            type_child = ch
            break
    declared_type, data_type = _scalar_type_and_dt(type_child)
    row: dict[str, Any] = {
        "name": name,
        "value_reference": value_reference,
        "causality": causality or None,
        "variability": variability or None,
        "declared_type": declared_type,
        "data_type": data_type,
    }
    if type_child is not None and type_child.attrib.get("start") is not None:
        row["start"] = type_child.attrib.get("start")
    if type_child is not None and type_child.attrib.get("unit") is not None:
        row["unit"] = type_child.attrib.get("unit")
    if ea.get("description"):
        row["description"] = ea["description"]
    return row


def _collect_scalar_variables(root: ET.Element) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for el in root.iter():
        if _local_name(el.tag) != "ScalarVariable":
            continue
        row = _scalar_variable_row(el)
        if row is not None:
            out.append(row)
    return out


def _model_description_result_dict(
    *,
    fmi_version: str,
    guid: str,
    model_identifier: str,
    description: str,
    author: str,
    model_version: str,
    generation_tool: str,
    generation_date: str,
    fmu_type: str,
    step_size_hint: float | None,
    start_time: float | None,
    stop_time: float | None,
    scalar_variables: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "fmi_version": fmi_version or "2.0",
        "guid": guid,
        "model_identifier": model_identifier,
        "description": description,
        "author": author,
        "model_version": model_version,
        "generation_tool": generation_tool,
        "generation_date": generation_date,
        "fmu_type": fmu_type,
        "step_size_hint": step_size_hint,
        "start_time": start_time,
        "stop_time": stop_time,
        "scalar_variables": scalar_variables,
    }


def parse_model_description_xml(xml_bytes: bytes) -> dict[str, Any]:
    """Parse FMI 2.0 ``modelDescription`` root (namespaced or plain tags)."""
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        raise FmuInspectError(f"Invalid modelDescription.xml: {exc}") from exc

    if _local_name(root.tag) != "fmiModelDescription":
        raise FmuInspectError("Root element is not fmiModelDescription.")

    (
        fmi_version,
        guid,
        model_identifier,
        description,
        author,
        model_version,
        generation_tool,
        generation_date,
    ) = _parse_md_root_attribs(root.attrib)
    if fmi_version.startswith("3"):
        raise FmuInspectError("FMI 3 modelDescription is not supported yet; use FMI 2.0.")

    fmu_type = _infer_fmu_type(root)
    step_size_hint, start_time, stop_time = _parse_default_experiment_times(root)
    scalar_variables = _collect_scalar_variables(root)

    return _model_description_result_dict(
        fmi_version=fmi_version,
        guid=guid,
        model_identifier=model_identifier,
        description=description,
        author=author,
        model_version=model_version,
        generation_tool=generation_tool,
        generation_date=generation_date,
        fmu_type=fmu_type,
        step_size_hint=step_size_hint,
        start_time=start_time,
        stop_time=stop_time,
        scalar_variables=scalar_variables,
    )

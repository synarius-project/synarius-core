"""Create mixed variants of maximal parameter sets (missing/changed/same = ~1/3 each).

Die drei Gruppen werden per Zufall (festem Seed) aus allen Kenngrößen gezogen — nicht mehr
das alphabetisch erste Drittel „missing“, damit ParaWiz-Zeilen (sortiert nach Name) gemischt
wirken.

Bei DCM werden geänderte Blöcke je Kenngröße zufällig nur Werte, nur Achsen (ST/X, ST/Y) oder
beides angepasst (ebenfalls seed-stabil pro Name).

Outputs:
- tests/testdata/parameter_formats/dcm/dcm2_maximal_10000_kennwerte_mixed_3way.dcm
- tests/testdata/parameter_formats/cdfx/cdfx_maximal_10000_kennwerte_mixed_3way.cdfx
- tests/testdata/parameter_formats/cdfx/cdfx_maximal_10000_kennwerte_with_a2l_dependency_mixed_3way.cdfx
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from pathlib import Path

# Reproduzierbare „Zufalls“-Aufteilung / Mutationswahl
_PARTITION_SEED = 42

_TOKENS = ("FESTWERT", "FESTWERTEBLOCK", "KENNLINIE", "KENNFELD", "STUETZSTELLENVERTEILUNG")
_NUM_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
_INST_RE = re.compile(r"(?s)(\s*<SW-INSTANCE>.*?</SW-INSTANCE>\s*)")
_SHORT_RE = re.compile(r"<SHORT-NAME>([^<]+)</SHORT-NAME>")
_SWVAL_RE = re.compile(r"(?s)(<SW-VALUES-PHYS>)(.*?)(</SW-VALUES-PHYS>)")
_V_RE = re.compile(r"(<V>)([-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)(</V>)")
_VT_RE = re.compile(r"(<VT[^>]*>)(.*?)(</VT>)", re.DOTALL)


@dataclass(frozen=True)
class DcmBlock:
    kind: str
    name: str
    lines: list[str]


def _mutate_num_str(s: str, name_seed: int, *, keep_int: bool) -> str:
    v = float(s)
    factor = 1.0 + 0.01 * (1 + (name_seed % 7))
    offs = (name_seed % 13) * 0.031
    nv = v * factor + offs
    if keep_int and "." not in s and "e" not in s.lower():
        return str(int(round(nv)))
    return f"{nv:.6f}".rstrip("0").rstrip(".")


def _mutate_line_numbers(line: str, name_seed: int, *, keep_int: bool = False) -> str:
    def repl(m: re.Match[str]) -> str:
        return _mutate_num_str(m.group(0), name_seed, keep_int=keep_int)

    return _NUM_RE.sub(repl, line)


def _split_dcm_blocks(text: str) -> tuple[list[str], list[DcmBlock]]:
    lines = text.splitlines(keepends=True)
    header: list[str] = []
    blocks: list[DcmBlock] = []
    i = 0
    n = len(lines)
    while i < n:
        s = lines[i].strip()
        if s and s.split()[0] in _TOKENS:
            break
        header.append(lines[i])
        i += 1
    while i < n:
        s = lines[i].strip()
        if not s:
            i += 1
            continue
        parts = s.split()
        if parts[0] not in _TOKENS or len(parts) < 2:
            i += 1
            continue
        kind, name = parts[0], parts[1]
        blk: list[str] = [lines[i]]
        i += 1
        while i < n:
            blk.append(lines[i])
            if lines[i].strip() == "END":
                i += 1
                if i < n and not lines[i].strip():
                    blk.append(lines[i])
                    i += 1
                break
            i += 1
        blocks.append(DcmBlock(kind=kind, name=name, lines=blk))
    return header, blocks


def _mutate_dcm_block(block: DcmBlock, *, partition_seed: int = _PARTITION_SEED) -> DcmBlock:
    name_seed = sum(ord(c) for c in block.name)
    brng = random.Random((partition_seed * 1_315_423_911 + name_seed) & 0x7FFF_FFFF)
    # Bei geänderten Kennlinien/Kennfeldern sollen Achsen in der Mehrheit gleich bleiben:
    # ~72% nur Werte, ~18% Werte+Achsen, ~10% nur Achsen.
    roll = brng.random()
    if block.kind in ("FESTWERT", "FESTWERTEBLOCK"):
        mut_vals, mut_axes = True, False
    elif block.kind == "STUETZSTELLENVERTEILUNG":
        mut_vals, mut_axes = False, True
    else:
        if roll < 0.72:
            mut_vals, mut_axes = True, False
        elif roll < 0.90:
            mut_vals, mut_axes = True, True
        else:
            mut_vals, mut_axes = False, True
    seed = name_seed
    out: list[str] = []
    for ln in block.lines:
        st = ln.lstrip()
        is_wert = st.startswith("WERT ")
        is_axis = st.startswith("ST/X ") or st.startswith("ST/Y ")
        if block.kind == "FESTWERT" and is_wert and mut_vals:
            out.append(_mutate_line_numbers(ln, seed))
        elif block.kind == "FESTWERTEBLOCK" and is_wert and mut_vals:
            out.append(_mutate_line_numbers(ln, seed))
        elif block.kind == "KENNLINIE" and ((is_axis and mut_axes) or (is_wert and mut_vals)):
            out.append(_mutate_line_numbers(ln, seed))
        elif block.kind == "KENNFELD" and ((is_axis and mut_axes) or (is_wert and mut_vals)):
            out.append(_mutate_line_numbers(ln, seed))
        elif block.kind == "STUETZSTELLENVERTEILUNG" and st.startswith("ST/X ") and mut_axes:
            out.append(_mutate_line_numbers(ln, seed))
        else:
            out.append(ln)
    return DcmBlock(kind=block.kind, name=block.name, lines=out)


def _classify(names: list[str], rng: random.Random) -> tuple[set[str], set[str], set[str]]:
    unique = sorted(set(names))
    order = unique[:]
    rng.shuffle(order)
    n = len(order)
    k = n // 3
    missing = set(order[:k])
    changed = set(order[k : 2 * k])
    same = set(order[2 * k :])
    return missing, changed, same


def _write_dcm_variant(src: Path, dst: Path) -> tuple[int, int, int]:
    header, blocks = _split_dcm_blocks(src.read_text(encoding="utf-8"))
    rng = random.Random(_PARTITION_SEED)
    missing, changed, same = _classify([b.name for b in blocks], rng)
    out = list(header)
    for b in blocks:
        if b.name in missing:
            continue
        if b.name in changed:
            b = _mutate_dcm_block(b)
        out.extend(b.lines)
    dst.write_text("".join(out), encoding="utf-8")
    return len(missing), len(changed), len(same)


def _mutate_sw_values_phys(body: str, name_seed: int) -> str:
    def repl_v(m: re.Match[str]) -> str:
        raw = m.group(2)
        mut = _mutate_num_str(raw, name_seed, keep_int=("." not in raw and "e" not in raw.lower()))
        return f"{m.group(1)}{mut}{m.group(3)}"

    return _V_RE.sub(repl_v, body)


def _mutate_cdfx_instance(instance_xml: str, name: str) -> str:
    seed = sum(ord(c) for c in name)

    def repl_swval(m: re.Match[str]) -> str:
        return f"{m.group(1)}{_mutate_sw_values_phys(m.group(2), seed)}{m.group(3)}"

    txt = _SWVAL_RE.sub(repl_swval, instance_xml)

    def repl_vt(m: re.Match[str]) -> str:
        v = m.group(2)
        if v.endswith("_alt"):
            return m.group(0)
        return f"{m.group(1)}{v}_alt{m.group(3)}"

    txt = _VT_RE.sub(repl_vt, txt)
    return txt


def _write_cdfx_variant(src: Path, dst: Path) -> tuple[int, int, int]:
    text = src.read_text(encoding="utf-8")
    m = list(_INST_RE.finditer(text))
    if not m:
        raise ValueError(f"No SW-INSTANCE blocks found in {src}")
    names: list[str] = []
    blocks: list[tuple[int, int, str, str]] = []
    for it in m:
        blk = it.group(1)
        nm = _SHORT_RE.search(blk)
        if nm is None:
            continue
        name = nm.group(1).strip()
        names.append(name)
        blocks.append((it.start(1), it.end(1), name, blk))
    candidate_names = [n for n in names if n != "A2L_REFERENCE_FILE"]
    rng = random.Random(_PARTITION_SEED)
    missing, changed, same = _classify(candidate_names, rng)

    out_parts: list[str] = []
    cur = 0
    for start, end, name, blk in blocks:
        out_parts.append(text[cur:start])
        cur = end
        if name in missing:
            continue
        if name in changed:
            out_parts.append(_mutate_cdfx_instance(blk, name))
        else:
            out_parts.append(blk)
    out_parts.append(text[cur:])
    dst.write_text("".join(out_parts), encoding="utf-8")
    return len(missing), len(changed), len(same) + (1 if "A2L_REFERENCE_FILE" in names else 0)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    td = root / "tests" / "testdata" / "parameter_formats"

    dcm_src = td / "dcm" / "dcm2_maximal_10000_kennwerte.dcm"
    dcm_dst = td / "dcm" / "dcm2_maximal_10000_kennwerte_mixed_3way.dcm"
    dcm_stats = _write_dcm_variant(dcm_src, dcm_dst)
    print(f"DCM: missing={dcm_stats[0]} changed={dcm_stats[1]} same={dcm_stats[2]} -> {dcm_dst.name}")

    cdfx_src = td / "cdfx" / "cdfx_maximal_10000_kennwerte.cdfx"
    cdfx_dst = td / "cdfx" / "cdfx_maximal_10000_kennwerte_mixed_3way.cdfx"
    cdfx_stats = _write_cdfx_variant(cdfx_src, cdfx_dst)
    print(f"CDFX: missing={cdfx_stats[0]} changed={cdfx_stats[1]} same={cdfx_stats[2]} -> {cdfx_dst.name}")

    cdfx_a2l_src = td / "cdfx" / "cdfx_maximal_10000_kennwerte_with_a2l_dependency.cdfx"
    cdfx_a2l_dst = td / "cdfx" / "cdfx_maximal_10000_kennwerte_with_a2l_dependency_mixed_3way.cdfx"
    cdfx_a2l_stats = _write_cdfx_variant(cdfx_a2l_src, cdfx_a2l_dst)
    print(
        "CDFX+A2L: "
        f"missing={cdfx_a2l_stats[0]} changed={cdfx_a2l_stats[1]} same={cdfx_a2l_stats[2]} -> {cdfx_a2l_dst.name}"
    )


if __name__ == "__main__":
    main()


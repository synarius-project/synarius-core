# Parameter-Format Testdaten (DCM/CDFX)

Diese Beispieldateien wurden auf Basis oeffentlich zugaenglicher Quellen erstellt:

- ASAM CDF Wiki: https://www.asam.net/standards/detail/cdf/wiki/
- ASAM ECU_Description.zip (enthaelt Beispiel `ASAP2_Demo_V171.CDFX`):
  https://www.asam.net/index.php?eID=dumpFile&t=f&f=2132&token=1672c6611f14141ae705140149a9401141821de0
- ASAM MCD-2 MC (ASAP2 / A2L) Wiki:
  https://www.asam.net/standards/detail/mcd-2-mc/wiki/
- DCM-Beispielsnippets aus `mat2dcm`:
  - https://github.com/muellerj/mat2dcm
  - https://raw.githubusercontent.com/muellerj/mat2dcm/master/spec/festwert_spec.m
  - https://raw.githubusercontent.com/muellerj/mat2dcm/master/spec/festwerteblock_spec.m
  - https://raw.githubusercontent.com/muellerj/mat2dcm/master/spec/kennlinie_spec.m
  - https://raw.githubusercontent.com/muellerj/mat2dcm/master/spec/kennfeld_spec.m

Dateien:
- `dcm/dcm2_minimal_all_types_once.dcm` (mehrere Kennlinien/-felder mit unterschiedlichen Rastern und nichtlinearen Achsen/Werten; inkl. mehrdimensionalem `FESTWERTEBLOCK <nx> @ <ny>`)
- `dcm/dcm2_maximal_10000_kennwerte.dcm` (Stress: 10k Kenngroessen; Kennlinien/-felder variabel gross und nichtlinear; `FESTWERTEBLOCK` als Mix aus 1D und 2D (`<nx> @ <ny>`) — neu erzeugen mit `synarius-core/scripts/generate_dcm2_maximal_stress.py`)
- `dcm/dcm2_maximal_10000_kennwerte_mixed_3way.dcm` (Variante: 1/3 der Kenngroessen **zufaellig** (Seed 42) entfaellt, 1/3 **zufaellig** geaendert — je Block nur Werte, nur Achsen oder beides —, 1/3 identisch — erzeugbar mit `synarius-core/scripts/generate_maximal_mixed_variants.py`)
- `dcm/dcm2_invalid_example.dcm`
- `cdfx/cdfx_minimal_all_types_once.cdfx`
- `cdfx/cdfx_maximal_10000_kennwerte.cdfx`
- `cdfx/cdfx_maximal_10000_kennwerte_mixed_3way.cdfx` (Variante: wie DCM zufaellige 1/3/1/3/1/3-Partition (Seed 42); geaenderte Instanzen vollstaendig mutiert)
- `cdfx/cdfx_maximal_10000_kennwerte_with_a2l_dependency.cdfx`
- `cdfx/cdfx_maximal_10000_kennwerte_with_a2l_dependency_mixed_3way.cdfx` (wie oben, A2L-Referenz bleibt erhalten; Partition zufaellig wie DCM)
- `cdfx/cdfx_invalid_example.cdfx`
- `a2l/asap2_demo_v171_minimal.a2l`

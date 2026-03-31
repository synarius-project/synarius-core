## FMU test fixtures — third-party provenance

### Platform-specific BouncingBall (FMI 2.0 co-simulation)

- **Files:** `win64/BouncingBall.fmu`, `linux64/BouncingBall.fmu`, `darwin64/BouncingBall.fmu`
- **Source repository:** https://github.com/modelica/fmi-cross-check  
- **Paths in that repo:** `fmus/2.0/cs/<platform>/Test-FMUs/0.0.2/BouncingBall/BouncingBall.fmu`  
  where `<platform>` is `win64`, `linux64`, or `darwin64`.
- **Context:** These FMUs are part of the public FMI cross-check / test-FMU set used for interoperability testing.

If you replace these files, update the paths above to match the exact revision you imported.

### Additional copies in this folder (tutorial / examples)

- **Repository:** https://github.com/modelica/fmi-beginners-tutorial-2025  
- **Paths:**
  - `part3/tutorial_multiple_FMUs/fmus/BouncingBall.fmu` → may appear as `BouncingBall.fmu` at the root of this fixture directory
  - `part2/Controller_FMI3.fmu` → `Controller_FMI3.fmu`
  - `part2/Stimuli.fmu` → `Stimuli.fmu`
- **License statement from upstream README:** code under the 2-Clause BSD License; documentation under CC BY-SA 4.0.
- **Copyright:** Copyright (C) 2023 The Modelica Association Project FMI (see upstream for current wording).

Keep this file aligned with the exact sources whenever fixtures are added or refreshed.

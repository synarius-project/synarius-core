"""setuptools entry: copy ``Lib/std`` into the built package for wheels."""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools import setup
from setuptools.command.build_py import build_py


class build_py_copy_standard_library(build_py):
    def run(self) -> None:
        super().run()
        root = Path(__file__).resolve().parent
        lib = root / "Lib" / "std"
        if not lib.is_dir():
            return
        pkg = Path(self.build_lib) / "synarius_core" / "standard_library"
        pkg.mkdir(parents=True, exist_ok=True)
        for item in lib.iterdir():
            dest = pkg / item.name
            if item.is_file():
                shutil.copy2(item, dest)
            elif item.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)


setup(cmdclass={"build_py": build_py_copy_standard_library})

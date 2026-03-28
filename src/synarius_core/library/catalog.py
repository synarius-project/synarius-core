"""Load FMF libraries from disk and expose a generic tree for console navigation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from synarius_core.model.attribute_dict import AttributeDict


def _discover_library_roots() -> list[Path]:
    """Return unique library root directories (each contains ``libraryDescription.xml``)."""
    seen: set[Path] = set()
    ordered: list[Path] = []

    def add(path: Path) -> None:
        resolved = path.resolve()
        if resolved in seen:
            return
        seen.add(resolved)
        ordered.append(path)

    try:
        from synarius_core.standard_library import standard_library_root

        add(standard_library_root())
    except RuntimeError:
        pass

    here = Path(__file__).resolve().parent
    cur = here.parent
    for _ in range(12):
        lib_parent = cur / "Lib"
        if lib_parent.is_dir():
            for child in sorted(lib_parent.iterdir(), key=lambda p: p.name.lower()):
                if child.is_dir() and (child / "libraryDescription.xml").is_file():
                    add(child)
            break
        if cur.parent == cur:
            break
        cur = cur.parent

    return ordered


@dataclass
class ParsedFmflRef:
    file: str
    profile: str | None


@dataclass
class ParsedElement:
    element_id: str
    display_name: str
    description: str
    element_dir: Path
    ports: list[tuple[str, str, str]]  # kind, name, type
    fmfl: list[ParsedFmflRef]


@dataclass
class ParsedLibrary:
    root_path: Path
    fmf_version: str
    name: str
    version: str
    description: str
    vendor: str
    elements: list[ParsedElement] = field(default_factory=list)


class LibraryTreeNode:
    """Generic console tree node for FMF libraries (not part of the simulation ``Model``)."""

    def __init__(self, *, name: str, parent: LibraryTreeNode | None) -> None:
        self._name = name
        self.parent = parent
        self.children: list[LibraryTreeNode] = []
        self.attribute_dict = AttributeDict()
        self._install_core_attrs()

    def _install_core_attrs(self) -> None:
        self.attribute_dict["type"] = self.node_type
        self.attribute_dict.set_virtual(
            "name",
            getter=lambda: self._name,
            setter=None,
            writable=False,
        )
        self.attribute_dict.set_virtual(
            "prompt_path",
            getter=self._compute_prompt_path,
            setter=None,
            writable=False,
        )

    @property
    def name(self) -> str:
        return self._name

    @property
    def node_type(self) -> str:
        raise NotImplementedError

    def _compute_prompt_path(self) -> str:
        if self.parent is None:
            return "@libraries"
        parts: list[str] = []
        node: LibraryTreeNode | None = self
        while node is not None and node.parent is not None:
            parts.append(node.name)
            node = node.parent
        parts.reverse()
        return "@libraries/" + "/".join(parts)

    def get(self, key: str):
        return self.attribute_dict[key]

    def set(self, key: str, value) -> None:
        self.attribute_dict.set_value(key, value)

    def get_child(self, segment: str) -> LibraryTreeNode | None:
        for ch in self.children:
            if ch.name == segment:
                return ch
        return None


class LibrariesCatalogRoot(LibraryTreeNode):
    """Synthetic root under ``@libraries`` (lists installed libraries)."""

    @property
    def node_type(self) -> str:
        return "LIB.CATALOG_ROOT"


class LibraryContainerNode(LibraryTreeNode):
    """One loaded FMF library (manifest ``name`` is the path segment, e.g. ``std``)."""

    def __init__(
        self,
        *,
        name: str,
        parent: LibraryTreeNode | None,
        parsed: ParsedLibrary,
    ) -> None:
        super().__init__(name=name, parent=parent)
        self._parsed = parsed
        self.attribute_dict["fmf_version"] = parsed.fmf_version
        self.attribute_dict["library_version"] = parsed.version
        self.attribute_dict["vendor"] = parsed.vendor
        self.attribute_dict["description"] = parsed.description
        self.attribute_dict["root_path"] = str(parsed.root_path)

    @property
    def node_type(self) -> str:
        return "LIB.LIBRARY"


class LibraryElementNode(LibraryTreeNode):
    """One element from ``libraryDescription.xml`` (segment = element ``id``)."""

    def __init__(
        self,
        *,
        name: str,
        parent: LibraryTreeNode | None,
        parsed: ParsedElement,
        library_name: str,
    ) -> None:
        super().__init__(name=name, parent=parent)
        self.attribute_dict["element_id"] = parsed.element_id
        self.attribute_dict["display_name"] = parsed.display_name
        self.attribute_dict["library_name"] = library_name
        self.attribute_dict["description"] = parsed.description
        self.attribute_dict["element_path"] = str(parsed.element_dir)
        self.attribute_dict["ports"] = self._format_ports(parsed.ports)
        self.attribute_dict["fmfl_files"] = ", ".join(f.file for f in parsed.fmfl) if parsed.fmfl else ""

    @staticmethod
    def _format_ports(ports: list[tuple[str, str, str]]) -> str:
        if not ports:
            return ""
        return "; ".join(f"{kind}:{pname}({typ})" for kind, pname, typ in ports)

    @property
    def node_type(self) -> str:
        return "LIB.ELEMENT"


def _text(el: ET.Element | None) -> str:
    if el is None or el.text is None:
        return ""
    return el.text.strip()


def _parse_library_manifest(root_path: Path) -> ParsedLibrary:
    manifest = root_path / "libraryDescription.xml"
    tree = ET.parse(manifest)
    r = tree.getroot()
    if r.tag != "LibraryDescription":
        raise ValueError(f"Expected LibraryDescription root in {manifest}")
    fmf_version = r.attrib.get("fmfVersion") or ""
    name = r.attrib.get("name") or ""
    version = r.attrib.get("version") or ""
    if not name:
        raise ValueError(f"Library name missing in {manifest}")

    description = ""
    vendor = ""
    for child in r:
        if child.tag == "Description":
            description = _text(child)
        elif child.tag == "Vendor":
            vendor = _text(child)

    elements: list[ParsedElement] = []
    for container in r:
        if container.tag != "elements":
            continue
        for el in container:
            if el.tag != "Element":
                continue
            eid = el.attrib.get("id") or ""
            rel = el.attrib.get("path") or ""
            if not eid or not rel:
                continue
            elem_path = (root_path / rel).resolve()
            if not elem_path.is_file():
                raise ValueError(f"Element file missing for {eid}: {elem_path}")
            elements.append(_parse_element_description(elem_path, eid))

    return ParsedLibrary(
        root_path=root_path.resolve(),
        fmf_version=fmf_version,
        name=name,
        version=version,
        description=description,
        vendor=vendor,
        elements=elements,
    )


def _parse_element_description(element_xml: Path, fallback_id: str) -> ParsedElement:
    tree = ET.parse(element_xml)
    r = tree.getroot()
    if r.tag != "ElementDescription":
        raise ValueError(f"Expected ElementDescription in {element_xml}")
    eid = r.attrib.get("id") or fallback_id
    display = r.attrib.get("name") or eid
    element_dir = element_xml.parent

    description = ""
    ports: list[tuple[str, str, str]] = []
    fmfl: list[ParsedFmflRef] = []

    for child in r:
        if child.tag == "Description":
            description = _text(child)
        elif child.tag == "Ports":
            for p in child:
                if p.tag != "Port":
                    continue
                kind = p.attrib.get("kind") or ""
                pname = p.attrib.get("name") or ""
                typ = p.attrib.get("type") or "real"
                ports.append((kind, pname, typ))
        elif child.tag == "Behavior":
            for b in child:
                if b.tag != "FMFL":
                    continue
                f = b.attrib.get("file") or ""
                if not f:
                    continue
                prof = b.attrib.get("profile")
                fmfl.append(ParsedFmflRef(file=f, profile=prof))

    return ParsedElement(
        element_id=eid,
        display_name=display,
        description=description,
        element_dir=element_dir,
        ports=ports,
        fmfl=fmfl,
    )


class LibraryCatalog:
    """Discover, parse, and hold FMF libraries; builds a console navigation tree."""

    def __init__(self, *, extra_roots: Iterable[Path] | None = None) -> None:
        self._extra = list(extra_roots or ())
        self.load_errors: list[str] = []
        self.libraries: list[ParsedLibrary] = []
        self.root = LibrariesCatalogRoot(name="libraries", parent=None)
        self.reload()

    @classmethod
    def load_default(cls) -> LibraryCatalog:
        return cls()

    def reload(self) -> None:
        self.load_errors.clear()
        self.libraries.clear()
        self.root.children.clear()

        roots = _discover_library_roots()
        for p in self._extra:
            if p.is_dir() and (p / "libraryDescription.xml").is_file():
                roots.append(p)

        seen: set[Path] = set()
        for root_path in roots:
            rp = root_path.resolve()
            if rp in seen:
                continue
            seen.add(rp)
            try:
                parsed = _parse_library_manifest(root_path)
            except Exception as exc:
                self.load_errors.append(f"{root_path}: {exc}")
                continue
            self.libraries.append(parsed)

        lib_names_seen: set[str] = set()
        for parsed in sorted(self.libraries, key=lambda lib: lib.name):
            if parsed.name in lib_names_seen:
                self.load_errors.append(f"Duplicate library name '{parsed.name}' skipped: {parsed.root_path}")
                continue
            lib_names_seen.add(parsed.name)
            lib_node = LibraryContainerNode(name=parsed.name, parent=self.root, parsed=parsed)
            self.root.children.append(lib_node)
            for elem in sorted(parsed.elements, key=lambda e: e.element_id):
                elem_node = LibraryElementNode(
                    name=elem.element_id,
                    parent=lib_node,
                    parsed=elem,
                    library_name=parsed.name,
                )
                lib_node.children.append(elem_node)


__all__ = [
    "LibraryCatalog",
    "LibraryTreeNode",
    "LibrariesCatalogRoot",
    "LibraryContainerNode",
    "LibraryElementNode",
    "ParsedLibrary",
    "ParsedElement",
]

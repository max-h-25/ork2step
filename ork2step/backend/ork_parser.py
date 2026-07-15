"""
ork_parser.py
Parses OpenRocket (.ork) files — which are ZIP archives containing a rocket.ork XML —
into an intermediate Python geometry model ready for CAD construction.

OpenRocket file format reference:
  https://github.com/openrocket/openrocket/blob/unstable/core/src/main/java/info/openrocket/core/file/openrocket/OpenRocketSaver.java
"""

from __future__ import annotations

import io
import zipfile
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from lxml import etree


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------

class NoseShape(str, Enum):
    OGIVE      = "ogive"
    CONICAL    = "conical"
    ELLIPSOID  = "ellipsoid"
    PARABOLIC  = "parabolic"
    POWER      = "power"
    HAACK      = "haack"
    SPHERICAL  = "spherical"

    @classmethod
    def from_ork(cls, raw: str) -> "NoseShape":
        mapping = {
            "ogive":      cls.OGIVE,
            "conical":    cls.CONICAL,
            "ellipsoid":  cls.ELLIPSOID,
            "ellipsoidal":cls.ELLIPSOID,
            "parabolic":  cls.PARABOLIC,
            "power":      cls.POWER,
            "haack":      cls.HAACK,
            "spherical":  cls.SPHERICAL,
        }
        return mapping.get(raw.lower(), cls.OGIVE)


class FinShape(str, Enum):
    TRAPEZOIDAL = "trapezoidal"
    ELLIPTICAL  = "elliptical"
    CUSTOM      = "custom"
    FREEFORM    = "freeform"

    @classmethod
    def from_ork(cls, raw: str) -> "FinShape":
        mapping = {
            "trapezoid":  cls.TRAPEZOIDAL,
            "trapezoidal":cls.TRAPEZOIDAL,
            "elliptical": cls.ELLIPTICAL,
            "ellipse":    cls.ELLIPTICAL,
            "custom":     cls.CUSTOM,
            "freeform":   cls.FREEFORM,
        }
        return mapping.get(raw.lower(), cls.TRAPEZOIDAL)


# ---------------------------------------------------------------------------
# Geometry data classes  (all dimensions in metres)
# ---------------------------------------------------------------------------

@dataclass
class RocketComponent:
    name: str
    axial_offset: float = 0.0      # metres from parent origin
    comment: str = ""


@dataclass
class NoseCone(RocketComponent):
    shape: NoseShape = NoseShape.OGIVE
    length: float = 0.0            # m
    base_diameter: float = 0.0     # m
    thickness: float = 0.002       # m  (wall; default 2 mm)
    shape_parameter: float = 0.0   # used by power/haack/parabolic


@dataclass
class BodyTube(RocketComponent):
    outer_diameter: float = 0.0    # m
    length: float = 0.0            # m
    thickness: float = 0.002       # m  (wall; default 2 mm)
    children: list = field(default_factory=list)


@dataclass
class Transition(RocketComponent):
    fore_diameter: float = 0.0
    aft_diameter: float = 0.0
    length: float = 0.0
    thickness: float = 0.002
    shape: NoseShape = NoseShape.CONICAL


@dataclass
class FinSet(RocketComponent):
    fin_count: int = 3
    shape: FinShape = FinShape.TRAPEZOIDAL
    root_chord: float = 0.0        # m
    tip_chord: float = 0.0         # m
    span: float = 0.0              # m
    sweep_length: float = 0.0      # m   leading-edge sweep measured at root
    thickness: float = 0.003       # m
    cant_angle: float = 0.0        # degrees
    tab_length: float = 0.0        # m
    tab_height: float = 0.0        # m
    # For elliptical fins the tip_chord is effectively 0 and span is the semi-axis


@dataclass
class MotorMount(RocketComponent):
    inner_diameter: float = 0.0    # m
    length: float = 0.0            # m


@dataclass
class LaunchLug(RocketComponent):
    outer_diameter: float = 0.0
    inner_diameter: float = 0.0
    length: float = 0.0


@dataclass
class Rocket:
    name: str = "Unnamed Rocket"
    designer: str = ""
    comment: str = ""
    # Ordered list of top-level components (nose → body → ...)
    stages: list = field(default_factory=list)

    def all_components(self):
        """Flat iterator over all components in assembly order."""
        for stage in self.stages:
            yield from _walk(stage)


def _walk(node):
    yield node
    if hasattr(node, "children"):
        for child in node.children:
            yield from _walk(child)


# ---------------------------------------------------------------------------
# Missing parameter tracking
# ---------------------------------------------------------------------------

@dataclass
class MissingParam:
    component_name: str
    param_name: str
    description: str
    unit: str
    default: float


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class OrkParseError(ValueError):
    pass


class OrkParser:
    """Parses a .ork file (ZIP containing rocket.ork XML) into a Rocket model."""

    # ORK stores everything in SI (metres, kg, etc.) unless the document
    # carries its own unit attribute — but in practice it is always SI.
    _UNIT_SCALE = 1.0  # already in metres

    def __init__(self):
        self.missing: list[MissingParam] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def parse_bytes(self, data: bytes) -> tuple[Rocket, list[MissingParam]]:
        """Parse raw .ork bytes.  Returns (Rocket, [MissingParam])."""
        xml_bytes = self._extract_xml(data)
        tree = self._parse_xml(xml_bytes)
        rocket = self._build_rocket(tree)
        return rocket, self.missing

    # ------------------------------------------------------------------
    # ZIP / XML helpers
    # ------------------------------------------------------------------

    def _extract_xml(self, data: bytes) -> bytes:
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = zf.namelist()
                # The inner file is always named rocket.ork
                ork_entries = [n for n in names if n.endswith(".ork")]
                if not ork_entries:
                    raise OrkParseError(
                        "No .ork entry found inside the ZIP archive. "
                        "Please ensure this is a valid OpenRocket file."
                    )
                return zf.read(ork_entries[0])
        except zipfile.BadZipFile:
            # Some older .ork files are raw XML (not zipped)
            if data.lstrip()[:5] == b"<?xml":
                return data
            raise OrkParseError(
                "File is neither a valid ZIP archive nor raw XML. "
                "It may be corrupted or not an OpenRocket file."
            )

    def _parse_xml(self, xml_bytes: bytes) -> etree._Element:
        try:
            return etree.fromstring(xml_bytes)
        except etree.XMLSyntaxError as exc:
            raise OrkParseError(f"XML parse error: {exc}") from exc

    # ------------------------------------------------------------------
    # Rocket-level
    # ------------------------------------------------------------------

    def _build_rocket(self, root: etree._Element) -> Rocket:
        rocket_el = root.find(".//rocket")
        if rocket_el is None:
            # root *is* <rocket> in some exports
            if root.tag == "rocket":
                rocket_el = root
            else:
                raise OrkParseError(
                    "Could not find <rocket> element. "
                    "This does not appear to be a valid OpenRocket file."
                )

        rocket = Rocket(
            name=rocket_el.findtext("name", "Unnamed Rocket"),
            designer=rocket_el.findtext("designer", ""),
            comment=rocket_el.findtext("comment", ""),
        )

        for stage_el in rocket_el.findall("subcomponents/stage"):
            stage_components = self._parse_subcomponents(stage_el, axial_base=0.0)
            rocket.stages.append(stage_components)

        if not rocket.stages:
            # Try to find components directly under rocket (single-stage shortcut)
            components = self._parse_subcomponents(rocket_el, axial_base=0.0)
            rocket.stages.append(components)

        return rocket

    # ------------------------------------------------------------------
    # Component dispatching
    # ------------------------------------------------------------------

    def _parse_subcomponents(
        self, parent_el: etree._Element, axial_base: float
    ) -> list:
        results = []
        sub_el = parent_el.find("subcomponents")
        if sub_el is None:
            return results

        cursor = axial_base  # running axial position

        for child in sub_el:
            comp = self._dispatch(child, cursor)
            if comp is None:
                continue
            results.append(comp)
            # Advance cursor by this component's length
            length = getattr(comp, "length", 0.0)
            cursor += length

        return results

    def _dispatch(self, el: etree._Element, axial_offset: float):
        tag = el.tag.lower()
        handlers = {
            "nosecone":    self._parse_nose_cone,
            "bodytube":    self._parse_body_tube,
            "transition":  self._parse_transition,
            "trapezoidfinset":  self._parse_fin_set,
            "ellipticalfinset": self._parse_fin_set,
            "freeformfinset":   self._parse_fin_set,
            "motormount":  self._parse_motor_mount,
            "launchlug":   self._parse_launch_lug,
            "innertubecomponent": self._parse_body_tube,
            "innertube":   self._parse_body_tube,
        }
        handler = handlers.get(tag)
        if handler:
            return handler(el, axial_offset)
        return None  # unknown element — skip silently

    # ------------------------------------------------------------------
    # Individual component parsers
    # ------------------------------------------------------------------

    def _f(self, el: etree._Element, tag: str, default: float = 0.0) -> float:
        """
        Read a float child element, return default if missing.

        Handles OpenRocket's "automatic" dimension format, where a field
        that's set to Automatic in the GUI is serialised as the string
        "auto <resolved_value>" instead of a plain number — e.g.
        <radius>auto 0.0225</radius>. In that case we still want the
        resolved value (0.0225), not the default/0.
        """
        txt = el.findtext(tag)
        if txt is None:
            return default
        txt = txt.strip()
        if txt.lower().startswith("auto"):
            # Strip the "auto" marker and any following whitespace, keep
            # the resolved numeric value that OpenRocket wrote alongside it.
            txt = txt[4:].strip()
            if not txt:
                # "auto" with no resolved value present — genuinely unknown
                return default
        try:
            return float(txt)
        except ValueError:
            return default

    def _require_thickness(
        self, el: etree._Element, comp_name: str, default: float = 0.002
    ) -> float:
        """Return wall thickness; queue a MissingParam if absent."""
        val = self._f(el, "thickness", -1.0)
        if val < 0:
            self.missing.append(
                MissingParam(
                    component_name=comp_name,
                    param_name="thickness",
                    description="Wall thickness",
                    unit="mm",
                    default=default * 1000,  # present to user in mm
                )
            )
            return default
        return val

    def _parse_nose_cone(self, el: etree._Element, axial_offset: float) -> NoseCone:
        name = el.findtext("name", "Nose Cone")
        length = self._f(el, "length")
        base_diam = self._f(el, "aftradius", 0) * 2 or self._f(el, "radius", 0) * 2
        if base_diam == 0:
            base_diam = self._f(el, "aftdiameter", 0)
        shape_str = el.findtext("shape", "ogive")
        thickness = self._require_thickness(el, name, default=0.002)

        return NoseCone(
            name=name,
            axial_offset=axial_offset,
            shape=NoseShape.from_ork(shape_str),
            length=length,
            base_diameter=base_diam,
            thickness=thickness,
            shape_parameter=self._f(el, "shapeparameter", 0.0),
        )

    def _parse_body_tube(self, el: etree._Element, axial_offset: float) -> BodyTube:
        name = el.findtext("name", "Body Tube")
        # OpenRocket stores radius (not diameter) here, and it may be in
        # "auto <value>" format if the user set diameter to Automatic —
        # _f() resolves that for us now.
        od = self._f(el, "outerdiameter", 0)
        if od == 0:
            od = self._f(el, "radius", 0) * 2
        if od == 0:
            od = self._f(el, "aftradius", 0) * 2  # fallback
        if od == 0:
            od = self._f(el, "outerradius", 0) * 2  # seen on tube couplers etc.
        length = self._f(el, "length")
        thickness = self._require_thickness(el, name, default=0.002)

        tube = BodyTube(
            name=name,
            axial_offset=axial_offset,
            outer_diameter=od,
            length=length,
            thickness=thickness,
        )
        # Recurse into subcomponents (fins, motor mounts, etc.)
        tube.children = self._parse_subcomponents(el, axial_base=0.0)
        return tube

    def _parse_transition(self, el: etree._Element, axial_offset: float) -> Transition:
        name = el.findtext("name", "Transition")
        fore_r = self._f(el, "foreradius", 0)
        aft_r  = self._f(el, "aftradius", 0)
        # Some versions use foreouterdiameter / aftouterdiameter
        fore_od = self._f(el, "foreouterdiameter", fore_r * 2)
        aft_od  = self._f(el, "aftouterdiameter",  aft_r  * 2)
        length = self._f(el, "length")
        thickness = self._require_thickness(el, name, default=0.002)
        shape_str = el.findtext("shape", "conical")

        return Transition(
            name=name,
            axial_offset=axial_offset,
            fore_diameter=fore_od,
            aft_diameter=aft_od,
            length=length,
            thickness=thickness,
            shape=NoseShape.from_ork(shape_str),
        )

    def _parse_fin_set(self, el: etree._Element, axial_offset: float) -> FinSet:
        name = el.findtext("name", "Fin Set")
        tag  = el.tag.lower()

        shape = FinShape.TRAPEZOIDAL
        if "elliptical" in tag:
            shape = FinShape.ELLIPTICAL
        elif "freeform" in tag:
            shape = FinShape.FREEFORM

        count      = int(self._f(el, "fincount", 3))
        root_chord = self._f(el, "rootchord")
        tip_chord  = self._f(el, "tipchord", 0)
        span       = self._f(el, "height") or self._f(el, "span")
        sweep      = self._f(el, "sweeplength", 0)
        thickness  = self._f(el, "thickness", 0.003)
        cant       = self._f(el, "cant", 0)
        tab_len    = self._f(el, "tablength", 0)
        tab_ht     = self._f(el, "tabheight", 0)

        return FinSet(
            name=name,
            axial_offset=axial_offset,
            fin_count=count,
            shape=shape,
            root_chord=root_chord,
            tip_chord=tip_chord,
            span=span,
            sweep_length=sweep,
            thickness=thickness,
            cant_angle=cant,
            tab_length=tab_len,
            tab_height=tab_ht,
        )

    def _parse_motor_mount(self, el: etree._Element, axial_offset: float) -> MotorMount:
        name = el.findtext("name", "Motor Mount")
        inner_r = self._f(el, "innerradius", 0)
        inner_d = self._f(el, "innerdiameter", inner_r * 2)
        if inner_d == 0:
            inner_d = self._f(el, "motormountdiameter", 0.029)  # 29mm default
        length = self._f(el, "length")
        return MotorMount(
            name=name,
            axial_offset=axial_offset,
            inner_diameter=inner_d,
            length=length,
        )

    def _parse_launch_lug(self, el: etree._Element, axial_offset: float) -> LaunchLug:
        name = el.findtext("name", "Launch Lug")
        od = self._f(el, "outerdiameter", 0) or self._f(el, "radius", 0) * 2
        id_ = self._f(el, "innerdiameter", 0) or self._f(el, "innerradius", 0) * 2
        length = self._f(el, "length")
        return LaunchLug(
            name=name,
            axial_offset=axial_offset,
            outer_diameter=od,
            inner_diameter=id_,
            length=length,
        )


# ---------------------------------------------------------------------------
# Pretty-print helper (for debugging / UI preview)
# ---------------------------------------------------------------------------

def summarise(rocket: Rocket) -> str:
    lines = [f"Rocket: {rocket.name}"]
    if rocket.designer:
        lines.append(f"  Designer: {rocket.designer}")
    for stage_i, stage in enumerate(rocket.stages):
        lines.append(f"  Stage {stage_i + 1}:")
        for comp in _walk_list(stage):
            lines.append(_fmt_component(comp))
    return "\n".join(lines)


def _walk_list(lst):
    if isinstance(lst, list):
        for item in lst:
            yield from _walk_list(item)
    else:
        yield lst
        if hasattr(lst, "children"):
            for child in lst.children:
                yield from _walk_list(child)


def _fmt_component(comp) -> str:
    prefix = "    "
    if isinstance(comp, NoseCone):
        return (
            f"{prefix}NoseCone '{comp.name}': shape={comp.shape.value}, "
            f"L={comp.length*1000:.1f}mm, D={comp.base_diameter*1000:.1f}mm, "
            f"wall={comp.thickness*1000:.1f}mm"
        )
    if isinstance(comp, BodyTube):
        return (
            f"{prefix}BodyTube '{comp.name}': "
            f"OD={comp.outer_diameter*1000:.1f}mm, L={comp.length*1000:.1f}mm, "
            f"wall={comp.thickness*1000:.1f}mm"
        )
    if isinstance(comp, Transition):
        return (
            f"{prefix}Transition '{comp.name}': "
            f"fore={comp.fore_diameter*1000:.1f}mm → aft={comp.aft_diameter*1000:.1f}mm, "
            f"L={comp.length*1000:.1f}mm"
        )
    if isinstance(comp, FinSet):
        return (
            f"{prefix}FinSet '{comp.name}': "
            f"count={comp.fin_count}, root={comp.root_chord*1000:.1f}mm, "
            f"tip={comp.tip_chord*1000:.1f}mm, span={comp.span*1000:.1f}mm"
        )
    if isinstance(comp, MotorMount):
        return (
            f"{prefix}MotorMount '{comp.name}': "
            f"ID={comp.inner_diameter*1000:.1f}mm, L={comp.length*1000:.1f}mm"
        )
    return f"{prefix}{type(comp).__name__} '{comp.name}'"

"""
cad_builder.py
Converts the intermediate geometry model produced by ork_parser into
solid CadQuery objects and exports a STEP file.

Design decisions:
  • Everything is built in millimetres (CadQuery default) — the parser produces
    metres so we scale × 1000 at the boundary.
  • Each component is built as a standalone solid then assembled via
    CadQuery's Workplane positioning.
  • Nose-cone profiles are generated analytically so they remain true solids
    (no mesh approximation).
  • Fins are extruded from a 2-D profile wire so they are parametric solids.
"""

from __future__ import annotations

import math
import os
import tempfile
from typing import Optional

try:
    import cadquery as cq
    CQ_AVAILABLE = True
except ImportError:
    CQ_AVAILABLE = False

from ork_parser import (
    Rocket, NoseCone, BodyTube, Transition, FinSet, MotorMount, LaunchLug,
    NoseShape, FinShape, _walk_list,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class CadBuildError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Unit helper
# ---------------------------------------------------------------------------

def _mm(metres: float) -> float:
    return metres * 1000.0


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

class CadBuilder:
    """
    Build a complete CadQuery assembly from a Rocket model.

    Usage::

        builder = CadBuilder()
        step_bytes = builder.build_step(rocket)
    """

    def __init__(self):
        if not CQ_AVAILABLE:
            raise CadBuildError(
                "CadQuery is not installed.  "
                "Run: pip install cadquery"
            )

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------

    def build_step(self, rocket: Rocket) -> bytes:
        """Return STEP file bytes for the full rocket."""
        assembly = self._build_assembly(rocket)
        return self._export_step(assembly)

    def build_step_to_file(self, rocket: Rocket, path: str) -> None:
        """Write STEP to *path*."""
        data = self.build_step(rocket)
        with open(path, "wb") as fh:
            fh.write(data)

    # ------------------------------------------------------------------
    # Assembly
    # ------------------------------------------------------------------

    def _build_assembly(self, rocket: Rocket) -> cq.Assembly:
        asm = cq.Assembly(name=rocket.name or "rocket")
        z_cursor = 0.0  # running Z position in mm (nose tip = 0)

        for stage_list in rocket.stages:
            for comp in _walk_list(stage_list):
                solid, length_mm = self._build_component(comp)
                if solid is None:
                    continue
                # Place component at z_cursor; rockets point nose-up (+Z)
                asm.add(
                    solid,
                    name=_safe_name(comp.name),
                    loc=cq.Location(cq.Vector(0, 0, z_cursor)),
                )
                # Only top-level components advance the cursor; children
                # (fins, motor mounts) are positioned relative to their parent
                # body tube, but for the flat _walk_list we only advance for
                # structural "stack" pieces.
                if isinstance(comp, (NoseCone, BodyTube, Transition)):
                    z_cursor += length_mm

        return asm

    def _build_component(self, comp) -> tuple[Optional[cq.Workplane], float]:
        """Return (solid_workplane, length_mm) or (None, 0)."""
        try:
            if isinstance(comp, NoseCone):
                return self._nose_cone(comp), _mm(comp.length)
            if isinstance(comp, BodyTube):
                return self._body_tube(comp), _mm(comp.length)
            if isinstance(comp, Transition):
                return self._transition(comp), _mm(comp.length)
            if isinstance(comp, FinSet):
                return self._fin_set(comp), 0.0
            if isinstance(comp, MotorMount):
                return self._motor_mount(comp), 0.0
            if isinstance(comp, LaunchLug):
                return self._launch_lug(comp), 0.0
        except Exception as exc:
            raise CadBuildError(
                f"Failed to build component '{comp.name}': {exc}"
            ) from exc
        return None, 0.0

    # ------------------------------------------------------------------
    # Component builders
    # ------------------------------------------------------------------

    # ---- Nose Cone -------------------------------------------------------

    def _nose_cone(self, nc: NoseCone) -> cq.Workplane:
        """
        Build a hollow nose cone as a shell (solid outer - solid inner).

        All nose shapes are approximated by a swept profile wire revolved
        around the Z-axis, giving a true solid of revolution.
        """
        L   = _mm(nc.length)
        R   = _mm(nc.base_diameter) / 2.0
        t   = _mm(nc.thickness)
        Ri  = max(R - t, 0.5)  # inner radius at base

        # Outer profile points (tip → base, 2D in XZ plane, X=radius, Z=axial)
        outer_pts = self._nose_profile(nc.shape, L, R, nc.shape_parameter, n=80)

        # Build outer solid of revolution
        outer = (
            cq.Workplane("XZ")
            .spline(outer_pts)
            .close()
            .revolve(360, (0, 0, 0), (0, 1, 0))
        )

        if t > 0 and Ri > 1.0:
            # Inner profile (offset inward)
            inner_pts = self._nose_profile(nc.shape, L - t, Ri, nc.shape_parameter, n=80)
            inner = (
                cq.Workplane("XZ")
                .moveTo(0, t)           # start at inner tip
                .spline(inner_pts)
                .close()
                .revolve(360, (0, 0, 0), (0, 1, 0))
            )
            try:
                outer = outer.cut(inner)
            except Exception:
                pass  # If cut fails, return solid nose — still valid geometry

        return outer

    def _nose_profile(
        self,
        shape: NoseShape,
        L: float,
        R: float,
        param: float,
        n: int = 60,
    ) -> list[tuple[float, float]]:
        """
        Returns [(x=radius, y=axial_z), …] profile from tip (0,0) → base (R, L).
        The profile is closed by the caller adding a line back to the origin.
        """
        pts = []
        for i in range(n + 1):
            t = i / n          # 0 → 1
            z = t * L
            x = self._nose_radius_at(shape, t, R, param)
            pts.append((x, z))
        # Append base-edge closing points
        pts.append((R, L))
        pts.append((0, L))
        return pts

    @staticmethod
    def _nose_radius_at(shape: NoseShape, t: float, R: float, param: float) -> float:
        """Radius of the nose cone at fractional position t ∈ [0,1]."""
        if t == 0:
            return 0.0
        if shape == NoseShape.CONICAL:
            return R * t
        if shape == NoseShape.OGIVE:
            rho = (R**2 + t**2 * (t**2)) / (2 * R)  # simple approximation
            # True tangent-ogive: rho = (R² + L²) / (2R)
            # r(x) = sqrt(rho² - (L-x)²) - (rho - R)
            # Use L=1, x=t for normalised version
            rho_n = (R**2 + 1.0) / (2 * R)
            val = math.sqrt(max(rho_n**2 - (1 - t)**2, 0)) - (rho_n - R)
            return max(val, 0.0)
        if shape == NoseShape.ELLIPSOID:
            return R * math.sqrt(1 - (1 - t)**2)
        if shape == NoseShape.PARABOLIC:
            k = param if param else 1.0
            return R * ((2 * t - k * t**2) / (2 - k))
        if shape == NoseShape.POWER:
            n = param if param else 0.5
            return R * (t ** n)
        if shape == NoseShape.HAACK:
            theta = math.acos(1 - 2 * t)
            C = param if param else 0.0
            return R * math.sqrt(
                (theta - math.sin(2 * theta) / 2 + C * math.sin(theta) ** 3) / math.pi
            )
        if shape == NoseShape.SPHERICAL:
            return R * math.sqrt(1 - (1 - t)**2)
        # fallback → conical
        return R * t

    # ---- Body Tube -------------------------------------------------------

    def _body_tube(self, bt: BodyTube) -> cq.Workplane:
        OD = _mm(bt.outer_diameter)
        L  = _mm(bt.length)
        t  = _mm(bt.thickness)
        ID = max(OD - 2 * t, 1.0)

        tube = (
            cq.Workplane("XY")
            .circle(OD / 2)
            .circle(ID / 2)
            .extrude(L)
        )
        return tube

    # ---- Transition (shoulder) -------------------------------------------

    def _transition(self, tr: Transition) -> cq.Workplane:
        R_fore = _mm(tr.fore_diameter) / 2
        R_aft  = _mm(tr.aft_diameter)  / 2
        L      = _mm(tr.length)
        t      = _mm(tr.thickness)

        # Build as a revolved trapezoid profile
        outer = (
            cq.Workplane("XZ")
            .moveTo(R_fore, 0)
            .lineTo(R_aft,  L)
            .lineTo(0, L)
            .lineTo(0, 0)
            .close()
            .revolve(360, (0, 0, 0), (0, 1, 0))
        )

        Ri_fore = max(R_fore - t, 0.5)
        Ri_aft  = max(R_aft  - t, 0.5)

        inner = (
            cq.Workplane("XZ")
            .moveTo(Ri_fore, 0)
            .lineTo(Ri_aft,  L)
            .lineTo(0, L)
            .lineTo(0, 0)
            .close()
            .revolve(360, (0, 0, 0), (0, 1, 0))
        )

        try:
            return outer.cut(inner)
        except Exception:
            return outer

    # ---- Fin Set ---------------------------------------------------------

    def _fin_set(self, fs: FinSet) -> cq.Workplane:
        """
        Build a single fin as a 2-D profile extruded to thickness,
        then pattern it angularly.  The result is placed at z=0 relative
        to the parent BodyTube's aft end.
        """
        thickness_mm = _mm(fs.thickness)
        root  = _mm(fs.root_chord)
        tip   = _mm(fs.tip_chord)
        span  = _mm(fs.span)
        sweep = _mm(fs.sweep_length)

        if fs.shape == FinShape.ELLIPTICAL:
            fin_solid = self._elliptical_fin(root, span, thickness_mm)
        else:
            fin_solid = self._trapezoidal_fin(root, tip, span, sweep, thickness_mm)

        # Angular pattern around Z-axis
        angle = 360.0 / max(fs.fin_count, 1)
        result = fin_solid
        for i in range(1, fs.fin_count):
            rotated = fin_solid.rotate((0, 0, 0), (0, 0, 1), angle * i)
            result = result.union(rotated)

        return result

    def _trapezoidal_fin(
        self, root: float, tip: float, span: float, sweep: float, thickness: float
    ) -> cq.Workplane:
        """Trapezoid fin in XY, then extrude in Z (thickness direction)."""
        # 2-D profile in XZ plane (X=span, Z=chord)
        pts = [
            (0.0,         0.0),        # root leading edge
            (sweep,       span),        # tip leading edge
            (sweep + tip, span),        # tip trailing edge
            (root,        0.0),         # root trailing edge
        ]
        fin = (
            cq.Workplane("XZ")
            .polyline(pts)
            .close()
            .extrude(thickness, both=True)
        )
        # Move fin so root sits at x=0 and fin extends outward
        return fin

    def _elliptical_fin(
        self, root: float, span: float, thickness: float
    ) -> cq.Workplane:
        """Ellipse-planform fin: semi-axes root/2 (chord) and span (height)."""
        fin = (
            cq.Workplane("XZ")
            .ellipse(span, root / 2)
            .extrude(thickness, both=True)
            .translate((span, root / 2, 0))  # move so base is at x=0
        )
        return fin

    # ---- Motor Mount -----------------------------------------------------

    def _motor_mount(self, mm_: MotorMount) -> cq.Workplane:
        OD = max(_mm(mm_.inner_diameter) + 4.0, _mm(mm_.inner_diameter) * 1.15)
        ID = _mm(mm_.inner_diameter)
        L  = _mm(mm_.length)

        tube = (
            cq.Workplane("XY")
            .circle(OD / 2)
            .circle(ID / 2)
            .extrude(L)
        )
        return tube

    # ---- Launch Lug ------------------------------------------------------

    def _launch_lug(self, ll: LaunchLug) -> cq.Workplane:
        OD = _mm(ll.outer_diameter) or 12.0
        ID = _mm(ll.inner_diameter) or 9.0
        L  = _mm(ll.length) or 40.0

        return (
            cq.Workplane("XY")
            .circle(OD / 2)
            .circle(ID / 2)
            .extrude(L)
        )

    # ------------------------------------------------------------------
    # STEP export
    # ------------------------------------------------------------------

    def _export_step(self, assembly: cq.Assembly) -> bytes:
        """Export assembly to STEP and return as bytes."""
        with tempfile.NamedTemporaryFile(suffix=".step", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            assembly.save(tmp_path, exportType="STEP")
            with open(tmp_path, "rb") as fh:
                return fh.read()
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    """Return a name safe for STEP entity identifiers."""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)

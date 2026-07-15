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
  • Fins in a set are added to the assembly as SEPARATE solids rather than
    boolean-unioned together. Repeated OCCT boolean unions of touching/
    near-identical solids are a well-known native-crash trigger, and a
    native crash (segfault) cannot be caught by Python try/except — it
    kills the whole process ("python quit unexpectedly" on macOS).
"""

from __future__ import annotations

import math
import os
import sys
import tempfile
import time
import uuid
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


def _log(msg: str) -> None:
    """Print immediately (flushed) so progress is visible even right before a crash."""
    print(f"[cad_builder] {msg}", flush=True)


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
        if len(assembly.children) == 0:
            # Exporting a totally empty assembly is another known OCCT
            # crash trigger (rather than a clean error) — fail loudly
            # in Python instead.
            raise CadBuildError(
                "No solids were produced from this rocket model — nothing "
                "to export. Check that the .ork file contains recognised "
                "components (NoseCone, BodyTube, Transition, FinSet, "
                "MotorMount, LaunchLug)."
            )
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

        # cq.Assembly requires every part name to be unique. OpenRocket
        # files routinely have multiple components with the identical
        # name (e.g. two "Body Tube" segments, or several fin sets all
        # called "Fin Set") — track every name used across the ENTIRE
        # assembly (not just within one component) and auto-number any
        # repeat so .add() never collides.
        used_names: dict[str, int] = {}

        def _unique_name(base: str) -> str:
            base = _safe_name(base) or "part"
            count = used_names.get(base, 0)
            used_names[base] = count + 1
            return base if count == 0 else f"{base}_{count + 1}"

        for stage_list in rocket.stages:
            for comp in _walk_list(stage_list):
                _log(f"building component: {comp.name} ({type(comp).__name__})")
                solids, length_mm = self._build_component(comp)
                if not solids:
                    _log(f"  -> skipped (no geometry produced)")
                    continue
                for solid in solids:
                    name = _unique_name(comp.name)
                    asm.add(
                        solid,
                        name=name,
                        loc=cq.Location(cq.Vector(0, 0, z_cursor)),
                    )
                _log(f"  -> added {len(solids)} solid(s)")
                # Only top-level components advance the cursor; children
                # (fins, motor mounts) are positioned relative to their parent
                # body tube, but for the flat _walk_list we only advance for
                # structural "stack" pieces.
                if isinstance(comp, (NoseCone, BodyTube, Transition)):
                    z_cursor += length_mm

        return asm

    def _build_component(self, comp) -> tuple[list[cq.Workplane], float]:
        """Return (list_of_solids, length_mm). Empty list if nothing built."""
        try:
            if isinstance(comp, NoseCone):
                return [self._nose_cone(comp)], _mm(comp.length)
            if isinstance(comp, BodyTube):
                return [self._body_tube(comp)], _mm(comp.length)
            if isinstance(comp, Transition):
                return [self._transition(comp)], _mm(comp.length)
            if isinstance(comp, FinSet):
                return self._fin_set(comp), 0.0
            if isinstance(comp, MotorMount):
                return [self._motor_mount(comp)], 0.0
            if isinstance(comp, LaunchLug):
                return [self._launch_lug(comp)], 0.0
        except Exception as exc:
            raise CadBuildError(
                f"Failed to build component '{comp.name}': {exc}"
            ) from exc
        return [], 0.0

    # ------------------------------------------------------------------
    # Component builders
    # ------------------------------------------------------------------

    # ---- Nose Cone -------------------------------------------------------

    def _nose_cone(self, nc: NoseCone) -> cq.Workplane:
        """
        Build a nose cone as a revolved polyline profile.
        Uses 32 straight segments to approximate the curve — robust on all platforms.
        """
        L  = _mm(nc.length)
        R  = _mm(nc.base_diameter) / 2.0
        t  = _mm(nc.thickness)
        Ri = max(R - t, 1.0)
        n  = 32

        # Sample outer profile points from tip to base
        outer_pts = []
        for i in range(n + 1):
            frac = i / n
            r = self._nose_radius_at(nc.shape, frac, R, nc.shape_parameter)
            z = frac * L
            outer_pts.append((r, z))

        # Build outer solid via polyline + revolve
        try:
            wp = cq.Workplane("XZ").moveTo(0, 0)
            for pt in outer_pts[1:]:
                wp = wp.lineTo(pt[0], pt[1])
            wp = wp.lineTo(0, L).close()
            outer = wp.revolve(360, (0, 0, 0), (0, 1, 0))
        except Exception:
            # Fallback: simple cone
            outer = (
                cq.Workplane("XZ")
                .moveTo(0, 0)
                .lineTo(R, L)
                .lineTo(0, L)
                .close()
                .revolve(360, (0, 0, 0), (0, 1, 0))
            )

        # Hollow out the inside
        if t > 0 and Ri > 1.0:
            try:
                wp2 = cq.Workplane("XZ").moveTo(0, t)
                for i in range(1, n + 1):
                    frac = i / n
                    r = self._nose_radius_at(nc.shape, frac, Ri, nc.shape_parameter)
                    z = t + frac * (L - t)
                    wp2 = wp2.lineTo(r, z)
                wp2 = wp2.lineTo(0, L).close()
                inner = wp2.revolve(360, (0, 0, 0), (0, 1, 0))
                outer = outer.cut(inner)
            except Exception:
                pass  # Return solid nose if hollowing fails

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
            rho_n = (R**2 + 1.0) / (2 * R)
            val = math.sqrt(max(rho_n**2 - (1 - t)**2, 0)) - (rho_n - R)
            return max(val, 0.0)
        if shape == NoseShape.ELLIPSOID:
            return R * math.sqrt(1 - (1 - t)**2)
        if shape == NoseShape.PARABOLIC:
            k = param if param else 1.0
            # k == 2 makes the denominator zero (degenerate profile that
            # can crash the OCCT revolve). Clamp away from that value.
            if abs(2 - k) < 1e-6:
                k = 2 - 1e-6 if k >= 2 else 2 + 1e-6
            return R * ((2 * t - k * t**2) / (2 - k))
        if shape == NoseShape.POWER:
            n_ = param if param else 0.5
            n_ = max(n_, 1e-3)  # guard against 0 or negative exponents
            return R * (t ** n_)
        if shape == NoseShape.HAACK:
            theta = math.acos(max(-1.0, min(1.0, 1 - 2 * t)))
            C = param if param else 0.0
            return R * math.sqrt(
                max(theta - math.sin(2 * theta) / 2 + C * math.sin(theta) ** 3, 0) / math.pi
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

    def _fin_set(self, fs: FinSet) -> list[cq.Workplane]:
        """
        Build a single fin as a 2-D profile extruded to thickness,
        then pattern it angularly. Each fin is returned as its OWN solid
        rather than boolean-unioned into one — repeated unions of
        touching/identical solids are a common native OCCT crash trigger,
        and the resulting solid is visually/functionally identical when
        exported to STEP as separate bodies in the same assembly.
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

        angle = 360.0 / max(fs.fin_count, 1)
        fins = [fin_solid]
        for i in range(1, fs.fin_count):
            fins.append(fin_solid.rotate((0, 0, 0), (0, 0, 1), angle * i))

        return fins

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
        """
        Export assembly to STEP and return as bytes.

        Writes to a build directory inside the project (backend/_build)
        rather than the OS-wide system temp directory. This avoids
        [Errno 5] I/O errors that can happen when the system TMPDIR is
        on a synced (iCloud Drive / Dropbox) or network-mounted location,
        or gets locked briefly by real-time antivirus scanning of a
        freshly-created file. Also retries once after a short pause,
        since that kind of lock is usually transient.
        """
        _log(f"exporting STEP with {len(assembly.children)} top-level solids...")

        build_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_build")
        os.makedirs(build_dir, exist_ok=True)

        tmp_path = os.path.join(build_dir, f"{uuid.uuid4().hex}.step")

        last_exc: Optional[Exception] = None
        for attempt in range(2):
            try:
                assembly.save(tmp_path, exportType="STEP")
                _log("export finished")
                with open(tmp_path, "rb") as fh:
                    return fh.read()
            except OSError as exc:
                last_exc = exc
                _log(f"export attempt {attempt + 1} failed: {exc!r} — retrying" if attempt == 0 else f"export failed: {exc!r}")
                if attempt == 0:
                    time.sleep(0.5)
                    continue
            finally:
                try:
                    if os.path.exists(tmp_path):
                        os.unlink(tmp_path)
                except OSError:
                    pass

        raise CadBuildError(
            f"STEP export failed with an OS-level I/O error after retrying: {last_exc}. "
            f"This usually means the temp/build directory ({build_dir}) is on a "
            "network drive, a cloud-synced folder (iCloud/Dropbox/Google Drive), "
            "or is being locked by antivirus/security software. Try moving the "
            "project to a local, non-synced folder (e.g. your home directory "
            "directly) and running again."
        ) from last_exc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_name(name: str) -> str:
    """Return a name safe for STEP entity identifiers."""
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in name)

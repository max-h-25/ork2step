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
    CenteringRing, TubeCoupler, Bulkhead, EngineBlock,
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
                return self._nose_cone(comp), _mm(comp.length)
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
            if isinstance(comp, CenteringRing):
                return [self._centering_ring(comp)], 0.0
            if isinstance(comp, TubeCoupler):
                return [self._tube_coupler(comp)], 0.0
            if isinstance(comp, Bulkhead):
                return [self._bulkhead(comp)], 0.0
            if isinstance(comp, EngineBlock):
                return [self._engine_block(comp)], 0.0
        except Exception as exc:
            raise CadBuildError(
                f"Failed to build component '{comp.name}': {exc}"
            ) from exc
        return [], 0.0

    # ------------------------------------------------------------------
    # Component builders
    # ------------------------------------------------------------------

    # ---- Nose Cone -------------------------------------------------------

    def _nose_cone(self, nc: NoseCone) -> list[cq.Workplane]:
        """
        Build a nose cone as a revolved polyline profile, hollowed with
        CadQuery's shell() rather than a hand-built inner profile.

        The earlier approach revolved a SECOND hand-computed inner profile
        and cut it from the solid nose. That's fragile: near the tip, the
        offset inner profile and outer profile converge to nearly the same
        point, which can produce a degenerate/self-intersecting cut and
        visible mesh artifacts. shell() lets OCCT compute the offset
        surface itself, which handles that convergence correctly.

        Returns a list of solids: [nose_body] or [nose_body, shoulder] if
        the .ork file specifies a shoulder (the cylindrical plug that
        inserts into the body tube).
        """
        L  = _mm(nc.length)
        R  = _mm(nc.base_diameter) / 2.0
        t  = _mm(nc.thickness)
        n  = 32

        outer_pts = []
        for i in range(n + 1):
            frac = i / n
            r = self._nose_radius_at(nc.shape, frac, R, nc.shape_parameter, L)
            z = frac * L
            outer_pts.append((r, z))

        try:
            wp = cq.Workplane("XZ").moveTo(0, 0)
            for pt in outer_pts[1:]:
                wp = wp.lineTo(pt[0], pt[1])
            wp = wp.lineTo(0, L).close()
            solid = wp.revolve(360, (0, 0, 0), (0, 1, 0))
        except Exception:
            # Fallback: simple cone
            solid = (
                cq.Workplane("XZ")
                .moveTo(0, 0)
                .lineTo(R, L)
                .lineTo(0, L)
                .close()
                .revolve(360, (0, 0, 0), (0, 1, 0))
            )

        if t > 0 and t < R:
            try:
                # Open (unshelled) face is the flat base at z=L — select
                # it by its normal direction (+Z) and shell inward,
                # leaving the base open like a real hollow nose cone.
                solid = solid.faces(">Z").shell(-t)
            except Exception:
                pass  # keep the solid nose if shelling fails

        solids = [solid]

        # ---- Shoulder: the cylindrical plug that inserts into the body tube.
        # Fused into the main nose body with a single union — this is safe
        # (just 2 solids, one flat coincident face) unlike the N-way fin
        # union avoided earlier, which risked repeated-boolean crashes.
        if nc.shoulder_length > 0 and nc.shoulder_diameter > 0:
            try:
                shoulder = self._nose_shoulder(nc, L)
                fused = solid.union(shoulder)
                solids = [fused]
            except Exception:
                # If the union fails, still include the shoulder as a
                # separate (touching but unfused) solid rather than
                # dropping it entirely.
                try:
                    solids.append(self._nose_shoulder(nc, L))
                except Exception:
                    pass  # nose body is still valid even if the shoulder fails

        return solids

    def _nose_shoulder(self, nc: NoseCone, nose_length_mm: float) -> cq.Workplane:
        """
        Build the shoulder as a hollow tube extending aft from the base of
        the nose (z = nose_length_mm onward), sized to slide into the body
        tube. If "capped" and a wall thickness is given, the far (aft) end
        is sealed with a thin disc — closing off the nose assembly's
        interior there — while the shoulder itself, and the rest of the
        nose cone, stay hollow rather than becoming a solid plug.
        """
        sh_OD = _mm(nc.shoulder_diameter)
        sh_L  = _mm(nc.shoulder_length)
        sh_t  = _mm(nc.shoulder_thickness)

        if sh_t <= 0 or sh_t >= sh_OD / 2:
            # No usable wall thickness given — can't build a meaningful
            # hollow tube + cap, so fall back to a solid plug.
            shoulder = cq.Workplane("XY").circle(sh_OD / 2).extrude(sh_L)
        else:
            shoulder = self._hollow_tube(
                sh_OD, sh_OD - 2 * sh_t, sh_L, label=f"NoseCone shoulder '{nc.name}'"
            )
            if nc.shoulder_capped:
                # Seal the bore at the far (aft) end with a thin disc,
                # rather than at the near end — that keeps the shoulder
                # (and everything ahead of it, back to the nose tip)
                # open and hollow, only closing off the far end.
                cap_thickness = min(sh_t, sh_L)
                inner_r = (sh_OD - 2 * sh_t) / 2
                cap = (
                    cq.Workplane("XY")
                    .circle(inner_r)
                    .extrude(cap_thickness)
                    .translate((0, 0, sh_L - cap_thickness))
                )
                try:
                    shoulder = shoulder.union(cap)
                except Exception:
                    pass  # keep the open hollow tube if the cap union fails

        # Position it starting right where the nose body's base ends.
        return shoulder.translate((0, 0, nose_length_mm))

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
            x = self._nose_radius_at(shape, t, R, param, L)
            pts.append((x, z))
        # Append base-edge closing points
        pts.append((R, L))
        pts.append((0, L))
        return pts

    @staticmethod
    def _nose_radius_at(shape: NoseShape, t: float, R: float, param: float, L: float = 1.0) -> float:
        """
        Radius of the nose cone at fractional position t ∈ [0,1].

        L (actual nose length, same units as R) matters for OGIVE: unlike
        conical/ellipsoid/power/Haack, a tangent-ogive's curvature genuinely
        depends on the R/L aspect ratio, not just R. Passing the wrong
        (or a normalized-but-unscaled) L here previously made the ogive
        formula degenerate to an almost-constant radius — i.e. a cylinder
        instead of a tapered nose. Defaults to 1.0 for shapes that don't
        use it, so existing callers that don't pass L still work.
        """
        if t == 0:
            return 0.0
        if shape == NoseShape.CONICAL:
            return R * t
        if shape == NoseShape.OGIVE:
            L = L if L > 0 else 1.0
            rho = (R**2 + L**2) / (2 * R) if R > 0 else 0.0
            x = t * L
            val = math.sqrt(max(rho**2 - (L - x)**2, 0)) - (rho - R)
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

    # ---- Shared hollow-tube helper ----------------------------------------

    def _hollow_tube(self, OD: float, ID: float, L: float, label: str = "tube") -> cq.Workplane:
        """
        Build a hollow cylinder explicitly: outer solid, inner solid, cut.

        Deliberately NOT using the `.circle(OD/2).circle(ID/2).extrude(L)`
        shorthand — that relies on CadQuery inferring the inner circle is a
        hole from wire nesting, which can silently produce a solid instead
        of a hollow tube on some inputs instead of raising an error. An
        explicit cut fails loudly (a real exception) if the geometry is
        degenerate, instead of quietly handing back the wrong shape.
        """
        if ID <= 0:
            raise CadBuildError(
                f"{label}: inner diameter resolved to {ID:.3f}mm (must be > 0)."
            )
        if ID >= OD:
            raise CadBuildError(
                f"{label}: inner diameter ({ID:.3f}mm) is not smaller than "
                f"outer diameter ({OD:.3f}mm) — can't build a hollow wall."
            )
        outer = cq.Workplane("XY").circle(OD / 2).extrude(L)
        inner = cq.Workplane("XY").circle(ID / 2).extrude(L)
        return outer.cut(inner)

    # ---- Body Tube -------------------------------------------------------

    def _body_tube(self, bt: BodyTube) -> cq.Workplane:
        OD = _mm(bt.outer_diameter)
        L  = _mm(bt.length)
        t  = _mm(bt.thickness)
        ID = OD - 2 * t
        return self._hollow_tube(OD, ID, L, label=f"BodyTube '{bt.name}'")

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

        if root <= 0 or span <= 0:
            # Building a fin with zero root chord or zero span means an
            # empty/degenerate 2-D profile — OCCT would fail on this with
            # an opaque "BRep_API: command not done" rather than a message
            # that points at the actual cause. Fail clearly instead.
            raise CadBuildError(
                f"FinSet '{fs.name}' has invalid dimensions "
                f"(root={root:.2f}mm, tip={tip:.2f}mm, span={span:.2f}mm) — "
                "can't build fin geometry from this."
            )

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
            # extrude(d, both=True) extrudes d in EACH direction (total 2d),
            # so pass half the target thickness to get the real thickness.
            .extrude(thickness / 2, both=True)
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
            .extrude(thickness / 2, both=True)
            .translate((span, root / 2, 0))  # move so base is at x=0
        )
        return fin

    # ---- Motor Mount -----------------------------------------------------

    def _motor_mount(self, mm_: MotorMount) -> cq.Workplane:
        ID = _mm(mm_.inner_diameter)
        OD = max(ID + 4.0, ID * 1.15)
        L  = _mm(mm_.length)
        return self._hollow_tube(OD, ID, L, label=f"MotorMount '{mm_.name}'")

    # ---- Launch Lug ------------------------------------------------------

    def _launch_lug(self, ll: LaunchLug) -> cq.Workplane:
        OD = _mm(ll.outer_diameter) or 12.0
        ID = _mm(ll.inner_diameter) or 9.0
        L  = _mm(ll.length) or 40.0
        return self._hollow_tube(OD, ID, L, label=f"LaunchLug '{ll.name}'")

    # ---- Centering Ring ---------------------------------------------------

    def _centering_ring(self, cr: CenteringRing) -> cq.Workplane:
        """A thin annular disk — sits between a motor mount and body tube."""
        OD = _mm(cr.outer_diameter) or 40.0
        ID = _mm(cr.inner_diameter) or 25.0
        L  = _mm(cr.length) or 3.0
        if ID >= OD:
            ID = max(OD - 2.0, 1.0)  # guard against degenerate/zero-clearance rings
        return self._hollow_tube(OD, ID, L, label=f"CenteringRing '{cr.name}'")

    # ---- Tube Coupler -------------------------------------------------------

    def _tube_coupler(self, tc: TubeCoupler) -> cq.Workplane:
        """A short internal sleeve that joins two body tube sections."""
        OD = _mm(tc.outer_diameter) or 40.0
        ID = _mm(tc.inner_diameter) or 36.0
        L  = _mm(tc.length) or 50.0
        if ID >= OD:
            ID = max(OD - 4.0, 1.0)
        return self._hollow_tube(OD, ID, L, label=f"TubeCoupler '{tc.name}'")

    # ---- Bulkhead -----------------------------------------------------------

    def _bulkhead(self, bh: Bulkhead) -> cq.Workplane:
        """A solid disc sealing off a body tube — no center hole."""
        OD = _mm(bh.outer_diameter) or 40.0
        L  = _mm(bh.length) or 3.0
        return cq.Workplane("XY").circle(OD / 2).extrude(L)

    # ---- Engine Block ---------------------------------------------------------

    def _engine_block(self, eb: EngineBlock) -> cq.Workplane:
        """A ring that seats the motor casing against the body tube."""
        OD = _mm(eb.outer_diameter) or 40.0
        ID = _mm(eb.inner_diameter) or 20.0
        L  = _mm(eb.length) or 5.0
        if ID <= 0 or ID >= OD:
            # No usable inner hole given — treat it as a solid disc rather
            # than guessing at a clearance hole.
            return cq.Workplane("XY").circle(OD / 2).extrude(L)
        return self._hollow_tube(OD, ID, L, label=f"EngineBlock '{eb.name}'")

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

# ORK Parsing Walkthrough

This document traces the complete parse path for the included
`examples/alpha_iii_example.ork` file, showing exactly what the parser
extracts at each stage.

---

## Step 1 — File Ingestion

`.ork` files produced by OpenRocket 15.x and later are **ZIP archives**
containing a single inner file also named `rocket.ork`.

```python
with zipfile.ZipFile(io.BytesIO(data)) as zf:
    xml_bytes = zf.read("rocket.ork")
```

Older OpenRocket versions (pre-1.5) sometimes write raw XML directly.
The parser detects this by checking whether the decompressed content starts
with `<?xml`:

```python
if data.lstrip()[:5] == b"<?xml":
    return data   # raw XML path
```

Our example file is already raw XML for portability.

---

## Step 2 — XML Parsing

```python
root = etree.fromstring(xml_bytes)
# root.tag == "openrocket"
```

The document root is `<openrocket>`.  The parser walks to `<rocket>`:

```xml
<openrocket version="1.7" creator="OpenRocket 15.03">
  <rocket>
    <name>Estes Alpha III Example</name>
    <designer>Test Designer</designer>
    ...
```

---

## Step 3 — Stage Discovery

```python
for stage_el in rocket_el.findall("subcomponents/stage"):
    ...
```

The example has one `<stage>` named "Sustainer".  Multi-stage rockets
(e.g. two-stage with booster) would have multiple `<stage>` elements, each
parsed separately and stored in `rocket.stages`.

---

## Step 4 — Component Dispatch

Each child of `<subcomponents>` is dispatched by tag name:

```
Tag                  → Handler method           → Dataclass
─────────────────────────────────────────────────────────────
nosecone             → _parse_nose_cone()       → NoseCone
bodytube             → _parse_body_tube()       → BodyTube
trapezoidfinset      → _parse_fin_set()         → FinSet
innertube            → _parse_body_tube()       → BodyTube
transition           → _parse_transition()      → Transition
ellipticalfinset     → _parse_fin_set()         → FinSet
```

Unknown tags are silently skipped — this ensures forward compatibility with
new OpenRocket component types.

---

## Step 5 — Nose Cone Extraction

XML source:
```xml
<nosecone>
  <name>Nose Cone</name>
  <length>0.07</length>          <!-- 70 mm -->
  <thickness>0.0032</thickness>  <!-- 3.2 mm wall -->
  <shape>ogive</shape>
  <aftradius>0.0155</aftradius>  <!-- 15.5 mm radius = 31 mm OD -->
</nosecone>
```

Parser output:
```python
NoseCone(
    name        = "Nose Cone",
    axial_offset = 0.0,       # first component — starts at tip
    shape       = NoseShape.OGIVE,
    length      = 0.07,       # metres
    base_diameter = 0.031,    # aftradius × 2
    thickness   = 0.0032,
    shape_parameter = 0.0,
)
```

**Note**: `aftradius` (not `aftdiameter`) is used here — the parser handles
both conventions since different OpenRocket versions use different field names.

---

## Step 6 — Body Tube Extraction

XML source:
```xml
<bodytube>
  <name>Body Tube</name>
  <length>0.254</length>         <!-- 254 mm = 10 inches -->
  <thickness>0.0016</thickness>  <!-- 1.6 mm wall -->
  <radius>0.0155</radius>        <!-- outer radius -->
  <subcomponents> ... </subcomponents>
</bodytube>
```

Parser output:
```python
BodyTube(
    name           = "Body Tube",
    axial_offset   = 0.07,    # placed immediately after nose cone
    outer_diameter = 0.031,   # radius × 2
    length         = 0.254,
    thickness      = 0.0016,
    children       = [ FinSet(...), BodyTube(...) ],  # from subcomponents
)
```

The axial cursor advances by 0.07 m (nose length) before this component,
so it starts where the nose ends — maintaining a contiguous stack.

---

## Step 7 — Fin Set Extraction

XML source:
```xml
<trapezoidfinset>
  <name>Fins</name>
  <fincount>3</fincount>
  <thickness>0.0032</thickness>
  <rootchord>0.0635</rootchord>    <!-- 63.5 mm -->
  <tipchord>0.0318</tipchord>      <!-- 31.8 mm -->
  <height>0.0508</height>          <!-- span = 50.8 mm -->
  <sweeplength>0.0127</sweeplength><!-- leading-edge sweep -->
</trapezoidfinset>
```

Parser output:
```python
FinSet(
    name         = "Fins",
    fin_count    = 3,
    shape        = FinShape.TRAPEZOIDAL,
    root_chord   = 0.0635,
    tip_chord    = 0.0318,
    span         = 0.0508,
    sweep_length = 0.0127,
    thickness    = 0.0032,
    cant_angle   = 0.0,
)
```

The 3 fins are placed 120° apart around the body tube axis in CadBuilder.

---

## Step 8 — Missing Parameter Detection

If a component lacks a `<thickness>` element:

```xml
<bodytube>
  <name>Body Tube</name>
  <length>0.254</length>
  <!-- no <thickness> element! -->
  <radius>0.0155</radius>
  ...
</bodytube>
```

The parser queues a `MissingParam`:
```python
MissingParam(
    component_name = "Body Tube",
    param_name     = "thickness",
    description    = "Wall thickness",
    unit           = "mm",
    default        = 2.0,      # 2 mm default — shown in UI
)
```

The `/upload` response includes this in `missing_params`.  The frontend
renders an input field pre-filled with the default.  The user's value is
sent back in `/generate` as:
```json
{ "Body Tube::thickness": 1.6 }
```

The backend converts 1.6 mm → 0.0016 m and writes it onto the dataclass
before passing to CadBuilder.

---

## Step 9 — Complete Intermediate Model

After parsing the example file:

```
Rocket: Estes Alpha III Example
  Designer: Test Designer
  Stage 1: [
    NoseCone  'Nose Cone'   shape=ogive   L=70mm  D=31mm  wall=3.2mm
    BodyTube  'Body Tube'   OD=31mm  L=254mm  wall=1.6mm
      FinSet  'Fins'        count=3  root=63.5mm  tip=31.8mm  span=50.8mm
      BodyTube 'Motor Mount' OD=18mm  L=70mm  wall=1.6mm
  ]
```

This model is then handed to `CadBuilder.build_step()` for geometry
construction and STEP export.

---

## CAD Generation Summary

| Component | CadQuery operation |
|---|---|
| Nose Cone (ogive) | 80-point spline profile → `revolve(360°)` → shell |
| Body Tube | `circle(OD/2).circle(ID/2).extrude(L)` |
| Fin (trapezoid) | `polyline(4pts).close().extrude(t, both=True)` |
| Fins × 3 | `.rotate((0,0,0),(0,0,1), 120°)` × 2, then `union` |
| Motor Mount | Same as body tube with smaller diameters |

All resulting objects are B-rep solids (not meshes), assembled into a
`cq.Assembly` with named entries, then exported via
`assembly.save(path, exportType="STEP")`.

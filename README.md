# ork2step — OpenRocket → STEP Converter

Convert `.ork` (OpenRocket) files into fully editable STEP solids for import
into Autodesk Fusion 360, FreeCAD, SolidWorks, or any STEP-capable CAD tool.

---

## Features

| Capability | Detail |
|---|---|
| **Nose cones** | Ogive, conical, ellipsoid, parabolic, power-series, Haack, spherical — including shoulder geometry if the .ork specifies one |
| **Body tubes** | Outer diameter, length, wall thickness → hollow shell |
| **Transitions** | Fore/aft diameters, conical or shaped shoulder |
| **Fin sets** | Trapezoidal, elliptical, freeform (approximated as a bounding trapezoid); angular pattern; tab geometry |
| **Motor mounts** | Inner tube as hollow cylinder |
| **Launch lugs** | Hollow cylinder at attachment point |
| **Centering rings** | Thin annular disc between motor mount and body tube |
| **Tube couplers** | Internal sleeve joining two body tube sections |
| **Bulkheads** | Solid disc sealing off a body tube |
| **Engine blocks** | Ring seating the motor casing against the tube |
| **Missing params** | UI prompts for wall thickness when absent from .ork |
| **Output** | AP214-compliant STEP — opens natively in Fusion 360 |

---

## Installation

There are two ways to run ork2step: **Docker** (easiest, works on any OS) or
**manual setup** (Python + Node.js installed directly on your machine).
Both are covered below — pick whichever suits you.

---

### Option A — Docker (recommended)

Docker bundles every dependency into containers, so you don't need Python,
Node.js, or any system libraries installed.

#### 1. Install Docker Desktop

| OS | Download |
|---|---|
| Windows | https://docs.docker.com/desktop/install/windows-install/ |
| macOS | https://docs.docker.com/desktop/install/mac-install/ |
| Linux | https://docs.docker.com/desktop/install/linux-install/ |

After installing, open Docker Desktop and wait for it to show **"Engine running"**
in the bottom-left corner before continuing.

#### 2. Download the project

**Without Git** — download the ZIP directly:

> **[⬇ Download ork2step.zip](https://github.com/max-h-25/ork2step/archive/refs/heads/main.zip)**

Once downloaded:
- **macOS**: double-click the ZIP to extract, then open Terminal and `cd` into the folder
- **Windows**: right-click → "Extract All", then open Command Prompt and `cd` into the folder
- **Linux**: `unzip ork2step.zip && cd ork2step`

**With Git:**
```bash
git clone https://github.com/max-h-25/ork2step.git
cd ork2step
```

#### 3. (macOS only) Set up the desktop icon

Open **Terminal**, paste this single line, and press Enter:

```bash
cd ~/Downloads/ork2step-main/ork2step && xattr -rd com.apple.quarantine . && chmod +x install.command start.command stop.command && ./install.command
```

> If your folder is named something different (like `ork2step 6`), replace `ork2step` in the `cd` path above with the actual folder name.

This strips the macOS security block from all files and creates a clickable **ork2step icon on your Desktop**.

From then on, just **double-click the Desktop icon** to launch — it starts Docker automatically, waits for everything to be ready, and opens your browser to `http://localhost:3000`.

To stop the app, double-click **`stop.command`** in the project folder.

> **If macOS says it "could not verify" `install.command` is free of malware:**
> That's normal Gatekeeper behavior for any script downloaded from the internet — not a sign anything's actually wrong. Right-clicking (or Ctrl-clicking) the file and choosing Open doesn't reliably bypass it. Instead, do it from Terminal: run the `cd ... && ./install.command` line above exactly as written. The `xattr -rd com.apple.quarantine` part strips the block before the script ever runs, so Gatekeeper won't stop it.

#### 4. Start manually (any OS)

If you prefer the terminal, or you're on Windows/Linux:

```bash
docker compose up --build
```

The first run downloads base images and installs all dependencies — this takes
3–10 minutes. Subsequent starts are fast (under 10 seconds).

When you see:
```
frontend  | Local:   http://localhost:3000/
backend   | Application startup complete.
```

go to **http://localhost:3000** in your browser.

To stop: press `Ctrl+C`, then `docker compose down`.

> **Apple Silicon (M1/M2/M3)**: the Dockerfiles are already configured for
> ARM64 — no extra steps needed.

---

### Option B — Manual setup (Python + Node.js)

Use this if you prefer not to use Docker, or want to modify the code and
see changes instantly.

#### Prerequisites

You need three things installed before starting. Check whether you already
have them:

```bash
python --version    # needs 3.10 or higher
node --version      # needs 18 or higher
npm --version       # comes with Node — any recent version is fine
```

If any of those commands fail or return an old version, install/update:

| Tool | Download |
|---|---|
| Python 3.10+ | https://www.python.org/downloads/ |
| Node.js 18+ | https://nodejs.org/ (choose the LTS version) |

> **Windows users**: when installing Python, tick **"Add Python to PATH"**
> on the first screen of the installer, or commands below won't work.

#### 1. Download the project

**Without Git** — download the ZIP directly:

> **[⬇ Download ork2step.zip](https://github.com/max-h-25/ork2step/archive/refs/heads/main.zip)**

Extract it, then open a terminal inside the `ork2step` folder.

**With Git:**
```bash
git clone https://github.com/max-h-25/ork2step.git
cd ork2step
```

#### 2. Set up the Python backend

Open a terminal and run these commands one at a time:

```bash
cd backend
```

Create a virtual environment (keeps dependencies isolated from the rest of
your system):

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate

# Windows (Command Prompt)
python -m venv .venv
.venv\Scripts\activate.bat

# Windows (PowerShell)
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Your terminal prompt should now start with `(.venv)` — this means the
virtual environment is active.

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

> **This step installs CadQuery**, which includes a pre-built geometry kernel
> (~200 MB). It may take a few minutes. If it fails, see the
> [CadQuery troubleshooting](#cadquery-installation-issues) section below.

Start the backend server:

```bash
uvicorn main:app --reload --port 8000
```

You should see:
```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

**Leave this terminal open.** The backend runs here while you use the app.

#### 3. Set up the frontend

Open a **second terminal** (keep the first one running the backend).

```bash
cd ork2step/frontend   # or just `cd ../frontend` if you're still in backend/
npm install
npm run dev
```

You should see:
```
  VITE v5.x.x  ready in xxx ms

  ➜  Local:   http://localhost:3000/
```

#### 4. Open the app

Go to **http://localhost:3000** in your browser.

#### 5. Stop the app

- Press `Ctrl+C` in the frontend terminal to stop the frontend.
- Press `Ctrl+C` in the backend terminal to stop the backend.

---

### CadQuery installation issues

CadQuery wraps the OpenCASCADE geometry kernel, which has platform-specific
requirements. Here's what to do if `pip install -r requirements.txt` fails:

**On Apple Silicon (M1/M2/M3 Mac)**

pip may not have a pre-built binary for ARM. Use conda instead:

```bash
# Install Miniconda if you don't have it:
# https://docs.conda.io/en/latest/miniconda.html

conda create -n ork2step python=3.11
conda activate ork2step
conda install -c cadquery -c conda-forge cadquery
pip install fastapi uvicorn python-multipart lxml pydantic
```

Then start the backend with the conda environment active:
```bash
uvicorn main:app --reload --port 8000
```

**On Linux (missing system libraries)**

```bash
sudo apt update
sudo apt install libgl1 libglu1-mesa libxrender1 libgomp1
pip install -r requirements.txt
```

**On any platform — if pip install times out or errors**

Try installing CadQuery separately first, then the rest:
```bash
pip install cadquery
pip install fastapi uvicorn python-multipart lxml pydantic
```

---

### Verify everything is working

Once both backend and frontend are running, open your browser to
**http://localhost:3000** and upload the included test file:

```
examples/alpha_iii_example.ork
```

You should see the rocket parsed (Estes Alpha III, 4 components), then be
able to click **Generate STEP File** and download a working `.step` file.
If that works, your installation is complete.

---

## Troubleshooting

### Same error keeps happening no matter what you change

If you've edited a backend file, or restarted the app, and it still behaves
like the old version — same bug, same error, no change at all — there's
almost always an **old backend process still running in the background**,
quietly answering requests instead of the one you just started. Python
doesn't reload a file just because it changed on disk; the old process
has to actually be killed.

This is especially likely if you ever closed a Terminal window/tab
instead of properly using `stop.command` — closing the window doesn't
reliably stop the backend process running underneath it, so it keeps
running and keeps holding onto port 8000.

**Fix — do this whenever things seem "stuck":**

```bash
lsof -i :8000
```

This lists whatever's currently using port 8000, including its PID
(process ID). Then:

```bash
kill -9 <PID>
```

(swap in the actual number from the previous command). Now restart the
app fresh — Desktop icon, or `./start.command`/`docker compose up --build`
— and try again. It's safe to run `lsof -i :8000` any time; if nothing's
running there, it just prints nothing.

**When to reach for this:**
- You edited `main.py`, `ork_parser.py`, or `cad_builder.py` directly
- You're not sure whether an earlier run of the app is still around
- A previous session's terminal got closed without running `stop.command`
- Generating a STEP file gives an error that doesn't match what the code
  currently does

### macOS says a `.command` file "could not verify" it's malware-free

Covered above in step 3 of the Docker install — right-clicking and choosing
Open isn't reliable for this; run it from Terminal instead so the
`xattr -rd com.apple.quarantine` step can strip the block first.

### A part is missing from the STEP output with no error shown

Check the parse summary shown after upload — any component type ork2step
doesn't support yet (bulkheads and engine blocks are supported now;
things like shock cords, parachutes, and multi-stage boosters/pods
currently aren't) is listed under **"Not yet supported — excluded from
the STEP output"** instead of just silently vanishing. If something's
missing and *isn't* listed there, that's worth reporting as a bug rather
than an expected gap.

---

```
ork2step/
├── backend/
│   ├── main.py          # FastAPI app — upload & generate endpoints
│   ├── ork_parser.py    # .ork XML parser → intermediate geometry model
│   ├── cad_builder.py   # CadQuery solid builder + STEP exporter
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── App.jsx      # Full React UI
│   │   └── main.jsx
│   ├── index.html
│   ├── vite.config.js
│   ├── package.json
│   └── Dockerfile
├── examples/
│   └── alpha_iii_example.ork   # Minimal test file (raw XML)
├── ork2step.app/                # macOS app bundle (desktop icon)
├── install.command              # Run once — creates Desktop icon
├── start.command                # Start the app manually
├── stop.command                 # Stop the app cleanly
├── docker-compose.yml
└── README.md
```

---

## Pipeline Overview

```
User uploads .ork
        │
        ▼
[ Upload Handler ]          POST /upload
        │  validates ZIP/XML structure
        ▼
[ OrkParser ]               ork_parser.py
        │  extracts: NoseCone, BodyTube, Transition, FinSet,
        │            MotorMount, LaunchLug, CenteringRing,
        │            TubeCoupler, Bulkhead, EngineBlock
        │  detects missing CAD params (wall thickness)
        ▼
[ Intermediate Model ]      Python dataclasses
        │  all dims in metres, component hierarchy preserved
        │  MissingParam list sent to UI
        ▼
  User fills missing params (if any)   POST /generate
        │
        ▼
[ CadBuilder ]              cad_builder.py
        │  NoseCone   → swept profile → revolve (solid of revolution)
        │  BodyTube   → annular extrusion
        │  Transition → revolved trapezoid
        │  FinSet     → extruded 2-D profile × N (angular pattern)
        │  MotorMount → annular extrusion
        │
        ▼
[ cq.Assembly ]             CadQuery assembly with named bodies
        │
        ▼
[ STEP exporter ]           assembly.save(..., exportType="STEP")
        │
        ▼
User downloads  rocket_name.step
```

---

## API Reference

### `POST /upload`

**Body**: `multipart/form-data`, field `file` = `.ork` file

**Response** (JSON):
```json
{
  "session_id": "uuid",
  "rocket_name": "Estes Alpha III",
  "summary": "Rocket: Estes Alpha III\n  Stage 1:\n    NoseCone ...",
  "component_count": 5,
  "missing_params": [
    {
      "component_name": "Body Tube",
      "param_name": "thickness",
      "description": "Wall thickness",
      "unit": "mm",
      "default": 2.0
    }
  ]
}
```

### `POST /generate`

**Body** (JSON):
```json
{
  "session_id": "uuid",
  "param_overrides": {
    "Body Tube::thickness": 1.6,
    "Nose Cone::thickness": 3.2
  }
}
```

**Response**: Binary STEP file (`application/octet-stream`).

### `GET /health`

Returns `{"status": "ok"}`.

---

## Nose Cone Geometry

Each nose shape is a true solid of revolution — not a mesh.  The profile
is sampled at 80 points and passed to CadQuery's spline → revolve pipeline.

| Shape | Formula `r(t)`, `t ∈ [0,1]` |
|---|---|
| Conical | `R·t` |
| Ogive | Tangent-ogive: `√(ρ²–(L–x)²) – (ρ–R)`, `ρ=(R²+L²)/2R` |
| Ellipsoid | `R·√(1–(1–t)²)` |
| Parabolic | `R·(2t – k·t²)/(2–k)` |
| Power-series | `R·tⁿ` |
| Haack (Von Kármán) | `R·√((θ–sin2θ/2+C·sin³θ)/π)` |

---

## Fusion 360 Import

1. Open Fusion 360.
2. **File → Open → Upload to Current Project** → select the `.step` file.
3. Each rocket component arrives as a separate **solid body** in the Bodies
   folder.
4. Use **Modify → Shell** to adjust wall thicknesses interactively.
5. Use **Assemble → Joint** or **As-Built Joint** to constrain parts.

> All geometry is parametric (B-rep solids), so you can edit sketches,
> extrusions, and revolves directly.  No mesh conversion required.

---

## Known Limitations

| Issue | Workaround |
|---|---|
| Freeform fins (spline outline) | Approximated as a bounding trapezoid (root/tip chord, span, sweep taken from the outline's extremes) — not an exact match to the curved outline. Edit further in Fusion 360 if needed. |
| Shock cords, parachutes | Not modelled — these don't produce CAD geometry; listed under "not yet supported" in the parse summary instead of silently vanishing |
| Multi-stage boosters and pods | Not yet supported — the parser currently only reads top-level stages, not nested parallel stages/pods. This is a bigger architectural change, not just a new shape. |
| Launch lug radial position | Placed at origin; move in Fusion 360 assembly |
| Very old .ork (pre-1.5) | May use a different XML schema — open a GitHub issue |
| Component names | Different OpenRocket versions serialize the name field as either `<name>` or the abbreviated `<n>` — the parser checks both, but if you hit a file where a name still doesn't come through right, that's worth reporting |

---

## Extending

**Add a new component type**: implement `_parse_<tag>` in `OrkParser` and
`_build_<type>` in `CadBuilder`.  The dispatch tables in both classes are the
only places that need updating.

**Switch to FreeCAD backend**: replace `cad_builder.py` with a FreeCAD Part
API implementation — the `Rocket` dataclass model is CAD-tool-agnostic.

---

## License

MIT — use freely, attribution appreciated.

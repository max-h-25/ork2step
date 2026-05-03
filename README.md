# ork2step — OpenRocket → STEP Converter

Convert `.ork` (OpenRocket) files into fully editable STEP solids for import
into Autodesk Fusion 360, FreeCAD, SolidWorks, or any STEP-capable CAD tool.

---

## Features

| Capability | Detail |
|---|---|
| **Nose cones** | Ogive, conical, ellipsoid, parabolic, power-series, Haack, spherical |
| **Body tubes** | Outer diameter, length, wall thickness → hollow shell |
| **Transitions** | Fore/aft diameters, conical or shaped shoulder |
| **Fin sets** | Trapezoidal, elliptical; angular pattern; tab geometry |
| **Motor mounts** | Inner tube as hollow cylinder |
| **Launch lugs** | Hollow cylinder at attachment point |
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
git clone https://github.com/your-username/ork2step.git
cd ork2step
```

#### 3. (macOS only) Set up the desktop icon

Run the installer once — it creates a clickable icon on your Desktop that
launches the app automatically from that point on:

```bash
double-click install.command
```

If macOS blocks it, right-click → Open → Open anyway.

From then on, just double-click the **ork2step icon on your Desktop** to start.
It will open Docker automatically, wait for containers to be ready, and open
your browser to `http://localhost:3000`.

To stop the app, double-click **`stop.command`** in the project folder.

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

> **[⬇ Download ork2step.zip](https://github.com/your-username/ork2step/archive/refs/heads/main.zip)**

Extract it, then open a terminal inside the `ork2step` folder.

**With Git:**
```bash
git clone https://github.com/your-username/ork2step.git
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

## Project Structure

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
        │  extracts: NoseCone, BodyTube, Transition,
        │            FinSet, MotorMount, LaunchLug
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
| Freeform fins (spline outline) | Rendered as trapezoid — edit in Fusion 360 |
| Launch lug radial position | Placed at origin; move in Fusion 360 assembly |
| Multi-stage ignition gaps | Stage separation modelled geometrically; no dynamics |
| Very old .ork (pre-1.5) | May use different XML schema — open a GitHub issue |

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

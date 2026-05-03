import { useState, useCallback, useRef } from "react";

const API = "http://localhost:8000";

// ─── Minimal design tokens ───────────────────────────────────────────────────
const S = {
  bg:      "#0a0e14",
  surface: "#111822",
  border:  "#1e2d40",
  accent:  "#00c8ff",
  accentD: "#0095c0",
  warn:    "#ffb830",
  ok:      "#36d87a",
  err:     "#ff4d6a",
  text:    "#e8f0f8",
  muted:   "#5a7490",
};

// ─── Tiny CSS-in-JS helper ───────────────────────────────────────────────────
const css = (obj) =>
  Object.entries(obj)
    .map(([k, v]) => `${k.replace(/[A-Z]/g, m => `-${m.toLowerCase()}`)}:${v}`)
    .join(";");

// ─── Sub-components ──────────────────────────────────────────────────────────

function RocketIcon({ size = 32, color = S.accent }) {
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none">
      <path d="M16 2C16 2 9 10 9 19a7 7 0 0014 0C23 10 16 2 16 2z" fill={color} opacity=".15" stroke={color} strokeWidth="1.5"/>
      <path d="M16 6c0 0-4.5 5.5-4.5 13" stroke={color} strokeWidth="1.2" strokeLinecap="round"/>
      <circle cx="16" cy="19" r="3" fill={color}/>
      <path d="M12 22l-3 5M20 22l3 5" stroke={color} strokeWidth="1.5" strokeLinecap="round"/>
      <path d="M9 15c-2 1-4 1.5-5 3M23 15c2 1 4 1.5 5 3" stroke={color} strokeWidth="1.2" strokeLinecap="round"/>
    </svg>
  );
}

function StepBadge({ step, current }) {
  const done = step < current;
  const active = step === current;
  return (
    <div style={{ display:"flex", alignItems:"center", gap:8 }}>
      <div style={{
        width:28, height:28, borderRadius:"50%", display:"flex",
        alignItems:"center", justifyContent:"center", fontSize:13, fontWeight:700,
        background: done ? S.ok : active ? S.accent : S.border,
        color: done || active ? S.bg : S.muted,
        flexShrink:0,
      }}>
        {done ? "✓" : step}
      </div>
    </div>
  );
}

function Card({ children, style = {} }) {
  return (
    <div style={{
      background: S.surface, border:`1px solid ${S.border}`,
      borderRadius:12, padding:24, ...style,
    }}>
      {children}
    </div>
  );
}

function Btn({ children, onClick, disabled, variant = "primary", style = {} }) {
  const variants = {
    primary: { background: S.accent, color: S.bg, border:"none" },
    outline: { background:"transparent", color: S.accent, border:`1px solid ${S.accent}` },
    danger:  { background:"transparent", color: S.err, border:`1px solid ${S.err}` },
  };
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        padding:"10px 22px", borderRadius:8, fontWeight:700, fontSize:14,
        cursor: disabled ? "not-allowed" : "pointer",
        opacity: disabled ? 0.4 : 1,
        transition:"all 0.15s", fontFamily:"inherit",
        ...variants[variant], ...style,
      }}
    >
      {children}
    </button>
  );
}

function Spinner() {
  return (
    <div style={{ display:"inline-block", width:20, height:20 }}>
      <style>{`
        @keyframes spin { to { transform:rotate(360deg) } }
      `}</style>
      <div style={{
        width:20, height:20, border:`2px solid ${S.border}`,
        borderTopColor: S.accent, borderRadius:"50%",
        animation:"spin 0.7s linear infinite",
      }}/>
    </div>
  );
}

function StatusBar({ type, message }) {
  const colors = { error: S.err, warning: S.warn, success: S.ok, info: S.accent };
  const icons  = { error:"✕", warning:"⚠", success:"✓", info:"ℹ" };
  const color  = colors[type] || S.muted;
  return (
    <div style={{
      display:"flex", alignItems:"flex-start", gap:10,
      padding:"12px 16px", borderRadius:8, marginTop:12,
      background:`${color}18`, border:`1px solid ${color}40`,
    }}>
      <span style={{ color, fontWeight:700, flexShrink:0 }}>{icons[type]}</span>
      <span style={{ color: S.text, fontSize:14, lineHeight:1.5 }}>{message}</span>
    </div>
  );
}

// ─── Upload Zone ─────────────────────────────────────────────────────────────

function UploadZone({ onUpload, loading }) {
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef();

  const handle = (file) => {
    if (!file) return;
    if (!file.name.toLowerCase().endsWith(".ork")) {
      alert("Please select a .ork OpenRocket file.");
      return;
    }
    onUpload(file);
  };

  return (
    <div
      onClick={() => !loading && inputRef.current.click()}
      onDragOver={e => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={e => {
        e.preventDefault(); setDragging(false);
        handle(e.dataTransfer.files[0]);
      }}
      style={{
        border:`2px dashed ${dragging ? S.accent : S.border}`,
        borderRadius:12, padding:"48px 32px", textAlign:"center",
        cursor: loading ? "wait" : "pointer",
        background: dragging ? `${S.accent}08` : "transparent",
        transition:"all 0.2s",
      }}
    >
      <input
        ref={inputRef}
        type="file" accept=".ork" style={{ display:"none" }}
        onChange={e => handle(e.target.files[0])}
      />
      {loading ? (
        <div style={{ display:"flex", flexDirection:"column", alignItems:"center", gap:16 }}>
          <Spinner/>
          <span style={{ color: S.muted, fontSize:14 }}>Parsing your rocket…</span>
        </div>
      ) : (
        <>
          <RocketIcon size={48} color={dragging ? S.accent : S.muted}/>
          <div style={{ marginTop:16, color: S.text, fontSize:16, fontWeight:600 }}>
            Drop your <span style={{ color: S.accent }}>.ork</span> file here
          </div>
          <div style={{ marginTop:6, color: S.muted, fontSize:13 }}>
            or click to browse — OpenRocket 15.x and earlier
          </div>
        </>
      )}
    </div>
  );
}

// ─── Rocket Summary ──────────────────────────────────────────────────────────

function RocketSummary({ summary, name, count }) {
  return (
    <div>
      <div style={{ display:"flex", alignItems:"center", gap:10, marginBottom:16 }}>
        <RocketIcon size={24}/>
        <span style={{ color: S.text, fontWeight:700, fontSize:16 }}>{name}</span>
        <span style={{
          marginLeft:"auto", background:`${S.accent}20`, color: S.accent,
          fontSize:12, fontWeight:700, padding:"3px 10px", borderRadius:20,
        }}>
          {count} components
        </span>
      </div>
      <pre style={{
        fontFamily:"'JetBrains Mono', 'Fira Code', monospace",
        fontSize:12, lineHeight:1.7, color: S.muted,
        background:`${S.bg}`, border:`1px solid ${S.border}`,
        borderRadius:8, padding:16, overflowX:"auto",
        maxHeight:220, overflowY:"auto", margin:0,
        whiteSpace:"pre-wrap", wordBreak:"break-word",
      }}>
        {summary}
      </pre>
    </div>
  );
}

// ─── Missing Params Form ─────────────────────────────────────────────────────

function MissingParamsForm({ params, values, onChange }) {
  if (params.length === 0) return null;
  return (
    <div>
      <div style={{ display:"flex", alignItems:"center", gap:8, marginBottom:16 }}>
        <span style={{ color: S.warn, fontSize:18 }}>⚠</span>
        <span style={{ color: S.text, fontWeight:700 }}>
          {params.length} parameter{params.length > 1 ? "s" : ""} need your input
        </span>
      </div>
      <div style={{ display:"flex", flexDirection:"column", gap:12 }}>
        {params.map(p => {
          const key = `${p.component_name}::${p.param_name}`;
          return (
            <div key={key} style={{
              display:"grid", gridTemplateColumns:"1fr auto",
              gap:12, alignItems:"center",
              padding:"14px 16px", borderRadius:8,
              background:`${S.warn}0a`, border:`1px solid ${S.warn}30`,
            }}>
              <div>
                <div style={{ color: S.text, fontSize:14, fontWeight:600 }}>
                  {p.component_name}
                  <span style={{ color: S.muted, fontWeight:400 }}> → {p.description}</span>
                </div>
                <div style={{ color: S.muted, fontSize:12, marginTop:2 }}>
                  Default: {p.default} {p.unit}
                </div>
              </div>
              <div style={{ display:"flex", alignItems:"center", gap:6 }}>
                <input
                  type="number"
                  step="0.1"
                  min="0"
                  value={values[key] ?? p.default}
                  onChange={e => onChange(key, parseFloat(e.target.value) || 0)}
                  style={{
                    width:80, padding:"8px 10px", borderRadius:6,
                    background: S.bg, border:`1px solid ${S.border}`,
                    color: S.text, fontSize:14, fontFamily:"inherit",
                    textAlign:"right",
                  }}
                />
                <span style={{ color: S.muted, fontSize:13, width:28 }}>{p.unit}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ─── Main App ────────────────────────────────────────────────────────────────

export default function App() {
  const [step, setStep] = useState(1);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [parseResult, setParseResult] = useState(null);
  const [paramValues, setParamValues] = useState({});

  const handleUpload = useCallback(async (file) => {
    setError(null);
    setLoading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const res = await fetch(`${API}/upload`, { method:"POST", body:fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `Upload failed (${res.status})`);
      setParseResult(data);
      // Pre-fill param values with defaults
      const defaults = {};
      for (const p of data.missing_params) {
        defaults[`${p.component_name}::${p.param_name}`] = p.default;
      }
      setParamValues(defaults);
      setStep(data.missing_params.length > 0 ? 2 : 3);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleGenerate = useCallback(async () => {
    setError(null);
    setLoading(true);
    try {
      const res = await fetch(`${API}/generate`, {
        method:"POST",
        headers:{ "Content-Type":"application/json" },
        body: JSON.stringify({
          session_id: parseResult.session_id,
          param_overrides: paramValues,
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || `Generation failed (${res.status})`);
      }
      // Trigger browser download
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${parseResult.rocket_name || "rocket"}.step`;
      a.click();
      URL.revokeObjectURL(url);
      setStep(4);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [parseResult, paramValues]);

  const reset = () => {
    setStep(1); setError(null);
    setParseResult(null); setParamValues({});
  };

  const steps = [
    { n:1, label:"Upload .ork" },
    { n:2, label:"Review Parameters" },
    { n:3, label:"Generate STEP" },
    { n:4, label:"Download" },
  ];

  return (
    <div style={{
      minHeight:"100vh", background: S.bg, color: S.text,
      fontFamily:"'IBM Plex Sans', system-ui, sans-serif",
      padding:"0 16px",
    }}>
      <style>{`
        @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;600;700&family=IBM+Plex+Mono&display=swap');
        * { box-sizing:border-box; margin:0; padding:0 }
        input:focus { outline:none; border-color:${S.accent} !important; }
        ::-webkit-scrollbar { width:6px; height:6px }
        ::-webkit-scrollbar-track { background:${S.bg} }
        ::-webkit-scrollbar-thumb { background:${S.border}; border-radius:3px }
        @keyframes fadeUp {
          from { opacity:0; transform:translateY(12px) }
          to   { opacity:1; transform:translateY(0) }
        }
        .fade-up { animation: fadeUp 0.35s ease both }
      `}</style>

      {/* Header */}
      <header style={{
        maxWidth:760, margin:"0 auto", padding:"32px 0 24px",
        display:"flex", alignItems:"center", gap:14,
        borderBottom:`1px solid ${S.border}`,
      }}>
        <RocketIcon size={36}/>
        <div>
          <div style={{ fontSize:22, fontWeight:700, letterSpacing:"-0.5px" }}>
            ork<span style={{ color: S.accent }}>2</span>step
          </div>
          <div style={{ fontSize:12, color: S.muted, marginTop:1 }}>
            OpenRocket → STEP for Fusion 360
          </div>
        </div>
        {step > 1 && (
          <button
            onClick={reset}
            style={{
              marginLeft:"auto", background:"transparent", border:"none",
              color: S.muted, fontSize:13, cursor:"pointer", fontFamily:"inherit",
            }}
          >
            ← Start over
          </button>
        )}
      </header>

      {/* Progress */}
      <div style={{ maxWidth:760, margin:"0 auto", padding:"20px 0" }}>
        <div style={{ display:"flex", gap:0 }}>
          {steps.map((s, i) => (
            <div key={s.n} style={{ display:"flex", alignItems:"center", flex:1 }}>
              <div style={{ display:"flex", alignItems:"center", gap:8 }}>
                <StepBadge step={s.n} current={step}/>
                <span style={{
                  fontSize:13, fontWeight:600,
                  color: s.n === step ? S.text : s.n < step ? S.ok : S.muted,
                }}>
                  {s.label}
                </span>
              </div>
              {i < steps.length - 1 && (
                <div style={{
                  flex:1, height:1, background: s.n < step ? S.ok : S.border,
                  margin:"0 12px", transition:"background 0.3s",
                }}/>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Main content */}
      <main style={{ maxWidth:760, margin:"0 auto", paddingBottom:64 }}>

        {/* Error */}
        {error && <StatusBar type="error" message={error}/>}

        {/* Step 1: Upload */}
        {step === 1 && (
          <Card style={{ marginTop:8 }} key="step1">
            <h2 style={{ fontSize:17, fontWeight:700, marginBottom:20, color: S.text }}>
              Upload your OpenRocket file
            </h2>
            <UploadZone onUpload={handleUpload} loading={loading}/>
            <StatusBar
              type="info"
              message="Supported: OpenRocket 15.x and earlier. The .ork file is a ZIP archive containing rocket geometry in XML format."
            />
          </Card>
        )}

        {/* Step 2 or 3: Summary + params */}
        {(step === 2 || step === 3) && parseResult && (
          <div className="fade-up" style={{ display:"flex", flexDirection:"column", gap:16, marginTop:8 }}>
            <Card>
              <RocketSummary
                summary={parseResult.summary}
                name={parseResult.rocket_name}
                count={parseResult.component_count}
              />
            </Card>

            {parseResult.missing_params.length > 0 && (
              <Card>
                <MissingParamsForm
                  params={parseResult.missing_params}
                  values={paramValues}
                  onChange={(key, val) => setParamValues(v => ({ ...v, [key]: val }))}
                />
              </Card>
            )}

            {parseResult.missing_params.length === 0 && (
              <StatusBar type="success" message="All parameters found — ready to generate!"/>
            )}

            <div style={{ display:"flex", gap:12, justifyContent:"flex-end" }}>
              <Btn variant="outline" onClick={reset}>Back</Btn>
              <Btn onClick={handleGenerate} disabled={loading}>
                {loading ? <Spinner/> : "⚙ Generate STEP File"}
              </Btn>
            </div>
          </div>
        )}

        {/* Step 4: Done */}
        {step === 4 && (
          <Card className="fade-up" style={{ marginTop:8, textAlign:"center", padding:"48px 32px" }}>
            <div style={{ fontSize:56 }}>🚀</div>
            <div style={{ fontSize:20, fontWeight:700, marginTop:16 }}>
              Your STEP file is downloading!
            </div>
            <div style={{ color: S.muted, fontSize:14, marginTop:8, lineHeight:1.6 }}>
              Import into Fusion 360 via <strong style={{ color: S.text }}>File → Open → Upload</strong> or drag the file
              directly onto the Fusion 360 canvas.  All bodies are editable solids.
            </div>

            <div style={{
              marginTop:28, padding:20, borderRadius:10,
              background:`${S.ok}0a`, border:`1px solid ${S.ok}30`,
              textAlign:"left",
            }}>
              <div style={{ color: S.ok, fontWeight:700, marginBottom:10 }}>Fusion 360 import tips</div>
              <ul style={{ color: S.muted, fontSize:13, lineHeight:2, paddingLeft:18 }}>
                <li>Each rocket stage/component arrives as a separate solid body</li>
                <li>Use <em>Assemble → Joint</em> to constrain parts to each other</li>
                <li>Shell/hollow features can be added with the <em>Shell</em> command</li>
                <li>All sketch dimensions are editable — use <em>Parametric</em> mode</li>
              </ul>
            </div>

            <Btn onClick={reset} style={{ marginTop:28 }}>Convert another file</Btn>
          </Card>
        )}
      </main>
    </div>
  );
}

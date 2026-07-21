import { useState } from "react";

import { apiUrl } from "./api";

const STATUS_LABEL = {
  pass: "Pass",
  review: "Needs Review",
  fail: "Fail",
  error: "Could Not Process",
};

const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png"];

// One dropzone for all three pickers (single image, batch images, batch CSV).
// Owns its own drag-highlight state; the parent only cares about the files.
function Dropzone({ title, sub, accept, multiple = false, onFiles }) {
  const [active, setActive] = useState(false);

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setActive(e.type === "dragenter" || e.type === "dragover");
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setActive(false);
    onFiles(e.dataTransfer.files);
  };

  return (
    <div
      className={`dropzone${active ? " dropzone-active" : ""}`}
      onDragEnter={handleDrag}
      onDragOver={handleDrag}
      onDragLeave={handleDrag}
      onDrop={handleDrop}
    >
      <label className="dropzone-label">
        <span className="dropzone-title">{title}</span>
        <span className="dropzone-sub">{sub}</span>
        <input
          type="file"
          accept={accept}
          multiple={multiple}
          className="dropzone-input"
          onChange={(e) => onFiles(e.target.files)}
        />
      </label>
    </div>
  );
}

function StatusBadge({ status }) {
  return <span className={`badge badge-${status}`}>{STATUS_LABEL[status] || status}</span>;
}

function FieldRow({ f }) {
  return (
    <tr>
      <td>{f.field.replace(/_/g, " ")}</td>
      <td><StatusBadge status={f.status} /></td>
      <td>{f.application_value}</td>
      <td>{f.extracted_value}</td>
      <td className="detail">{f.detail}</td>
    </tr>
  );
}

function ResultCard({ result }) {
  return (
    <div className="result-card">
      <div className="result-header">
        <strong>{result.filename}</strong>
        <StatusBadge status={result.overall_status} />
      </div>
      {result.error ? (
        <p className="error-text">{result.error}</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Field</th>
              <th>Status</th>
              <th>Application Says</th>
              <th>Label Shows</th>
              <th>Detail</th>
            </tr>
          </thead>
          <tbody>
            {result.fields.map((f) => (
              <FieldRow key={f.field} f={f} />
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function SingleVerifyForm() {
  const [file, setFile] = useState(null);
  const [form, setForm] = useState({
    brand_name: "",
    class_type: "",
    abv: "",
    net_contents: "",
    name_address: "",
    beverage_type: "distilled_spirits",
    is_imported: false,
    country_of_origin: "",
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const setImage = (fileList) => {
    const img = Array.from(fileList).find((f) => ACCEPTED_IMAGE_TYPES.includes(f.type));
    if (img) setFile(img);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) {
      setError("Please choose a label image first.");
      return;
    }
    setError("");
    setLoading(true);
    setResult(null);

    const body = new FormData();
    body.append("file", file);
    body.append(
      "application_data",
      JSON.stringify({ ...form, abv: parseFloat(form.abv) || 0 })
    );

    try {
      const resp = await fetch(apiUrl("/verify"), { method: "POST", body });
      if (!resp.ok) {
        const d = await resp.json();
        throw new Error(d.detail || "Verification failed");
      }
      setResult(await resp.json());
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit} className="form">
        <Dropzone
          title="Drag and Drop a Label Image, or Click to Browse"
          sub={`JPEG or PNG, up to 1.5MB${file ? ` — ${file.name}` : ""}`}
          accept={ACCEPTED_IMAGE_TYPES.join(",")}
          onFiles={setImage}
        />

        <p className="section-label">Add Application Information</p>

        <label>
          Alcohol Type
          <select
            value={form.beverage_type}
            onChange={(e) => setForm({ ...form, beverage_type: e.target.value })}
          >
            <option value="distilled_spirits">Distilled Spirits</option>
            <option value="wine">Wine</option>
            <option value="beer">Beer / Malt Beverage</option>
          </select>
        </label>

        <label>
          Brand Name
          <input
            type="text"
            placeholder='e.g. "Old Tom Distillery"'
            value={form.brand_name}
            onChange={(e) => setForm({ ...form, brand_name: e.target.value })}
            required
          />
        </label>

        <label>
          Class / Type
          <input
            type="text"
            placeholder='e.g. "Kentucky Straight Bourbon Whiskey"'
            value={form.class_type}
            onChange={(e) => setForm({ ...form, class_type: e.target.value })}
            required
          />
        </label>

        <label>
          Alcohol by Volume (%)
          <input
            type="number"
            step="0.1"
            placeholder="e.g. 45.0"
            value={form.abv}
            onChange={(e) => setForm({ ...form, abv: e.target.value })}
            required
          />
        </label>

        <label>
          Net Contents
          <input
            type="text"
            placeholder='e.g. "750 mL"'
            value={form.net_contents}
            onChange={(e) => setForm({ ...form, net_contents: e.target.value })}
            required
          />
        </label>

        <label>
          Bottled By (Name and Address)
          <input
            type="text"
            placeholder='e.g. "Bottled By Old Tom Distillery, Louisville, KY"'
            value={form.name_address}
            onChange={(e) => setForm({ ...form, name_address: e.target.value })}
            required
          />
        </label>

        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={form.is_imported}
            onChange={(e) => setForm({ ...form, is_imported: e.target.checked })}
          />
          Imported Product
        </label>

        {form.is_imported && (
          <label>
            Country of Origin
            <input
              type="text"
              placeholder='e.g. "Product of Scotland"'
              value={form.country_of_origin}
              onChange={(e) => setForm({ ...form, country_of_origin: e.target.value })}
            />
          </label>
        )}

        <button type="submit" disabled={loading}>
          {loading ? "Checking Label…" : "Check Label"}
        </button>
      </form>

      {error && <p className="error-text">{error}</p>}
      {result && <ResultCard result={result} />}
    </div>
  );
}

function BatchVerifyForm() {
  const [files, setFiles] = useState([]);
  const [csvFile, setCsvFile] = useState(null);
  const [summary, setSummary] = useState(null);
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [phase, setPhase] = useState("uploading");
  const [processDone, setProcessDone] = useState(0);
  const [processTotal, setProcessTotal] = useState(0);

  const addFiles = (fileList) => {
    const incoming = Array.from(fileList).filter((f) => ACCEPTED_IMAGE_TYPES.includes(f.type));
    if (incoming.length > 0) setFiles(incoming);
  };

  const setCsv = (fileList) => {
    const csv = Array.from(fileList).find(
      (f) => f.name.toLowerCase().endsWith(".csv") || f.type === "text/csv"
    );
    if (csv) setCsvFile(csv);
  };

  const downloadTemplate = () => {
    const header =
      "filename,beverage_type,brand_name,class_type,abv,net_contents,name_address,is_imported,country_of_origin";
    const example =
      'label1.jpg,distilled_spirits,Old Tom Distillery,Kentucky Straight Bourbon Whiskey,45.0,750 mL,"Bottled By Old Tom Distillery, Louisville, KY",false,';
    const blob = new Blob([header + "\n" + example + "\n"], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "application_data_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  // XHR (not fetch) so we get upload progress AND can parse the streamed
  // NDJSON response incrementally for live per-label processing progress.
  const uploadBatch = (body) =>
    new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", apiUrl("/verify/batch"));

      const acc = [];
      let seen = 0; // chars of responseText already parsed
      let summary = null;

      xhr.upload.onprogress = (ev) => {
        if (ev.lengthComputable) setUploadProgress(Math.round((ev.loaded / ev.total) * 100));
      };
      xhr.upload.onload = () => setPhase("processing");

      const parseNew = () => {
        const text = xhr.responseText;
        let nl;
        while ((nl = text.indexOf("\n", seen)) !== -1) {
          const line = text.slice(seen, nl).trim();
          seen = nl + 1;
          if (!line) continue;
          let msg;
          try {
            msg = JSON.parse(line);
          } catch {
            continue;
          }
          if (msg.type === "meta") {
            setProcessTotal(msg.total);
            setProcessDone(0);
          } else if (msg.type === "result") {
            acc.push(msg.result);
            setProcessDone(acc.length);
          } else if (msg.type === "summary") {
            summary = msg;
          }
        }
      };

      xhr.onprogress = parseNew;
      xhr.onload = () => {
        parseNew(); // flush any trailing line
        if (xhr.status >= 200 && xhr.status < 300) {
          acc.sort((a, b) => (a.filename < b.filename ? -1 : a.filename > b.filename ? 1 : 0));
          resolve({ results: acc, summary });
        } else {
          let d = null;
          try {
            d = JSON.parse(xhr.responseText);
          } catch {
            /* error body wasn't JSON */
          }
          reject(new Error((d && d.detail) || "Batch verification failed"));
        }
      };
      xhr.onerror = () => reject(new Error("Network error during upload"));
      xhr.send(body);
    });

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (files.length === 0) {
      setError("Please choose one or more label images.");
      return;
    }
    if (!csvFile) {
      setError("Please choose the application-data CSV file.");
      return;
    }
    setError("");
    setResults([]);
    setSummary(null);
    setUploadProgress(0);
    setProcessDone(0);
    setProcessTotal(0);
    setPhase("uploading");
    setLoading(true);

    const body = new FormData();
    files.forEach((f) => body.append("files", f));
    body.append("data_csv", csvFile);

    try {
      const { results, summary } = await uploadBatch(body);
      setResults(results);
      setSummary(summary);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <form onSubmit={handleSubmit} className="form">
        <Dropzone
          title="Drag and Drop Label Images, or Click to Browse"
          sub={`JPEG or PNG, up to 1.5MB, max of 300 files${
            files.length > 0 ? ` — ${files.length} selected` : ""
          }`}
          accept={ACCEPTED_IMAGE_TYPES.join(",")}
          multiple
          onFiles={addFiles}
        />

        <Dropzone
          title="Drag and Drop CSV File, or Click to Browse"
          sub={`up to 300${csvFile ? ` — ${csvFile.name}` : ""}`}
          accept=".csv,text/csv"
          onFiles={setCsv}
        />

        <button type="button" className="template-link" onClick={downloadTemplate}>
          Download CSV template
        </button>

        <button type="submit" disabled={loading}>
          {loading ? "Checking Batch…" : "Check Batch"}
        </button>

        {loading && (
          <div className="progress" aria-live="polite">
            <div className="progress-track">
              <div
                className="progress-fill"
                style={{
                  width: `${
                    phase === "uploading"
                      ? uploadProgress
                      : processTotal
                      ? Math.round((processDone / processTotal) * 100)
                      : 0
                  }%`,
                }}
              />
            </div>
            <p className="progress-label">
              {phase === "uploading"
                ? `Uploading ${files.length} file${files.length === 1 ? "" : "s"}… ${uploadProgress}%`
                : `Verifying labels… ${processDone} / ${processTotal || "…"}`}
            </p>
            {/* Nothing is persisted server-side (ADR.md §1), so leaving the page
                discards the whole batch -- there is no run to come back to. */}
            <p className="progress-warning">
              Please do not refresh or leave this page — results will be lost and
              the batch will need to start over.
            </p>
          </div>
        )}
      </form>

      {error && <p className="error-text">{error}</p>}

      {summary && (
        <p className="summary">
          {summary.total} labels checked — {summary.passed} pass, {summary.review} need review,{" "}
          {summary.failed} fail, {summary.errored} could not be processed.
        </p>
      )}

      {results.map((r, i) => (
        // Index, not filename: a batch can contain duplicate filenames.
        <ResultCard key={i} result={r} />
      ))}
    </div>
  );
}

const RESOURCES = [
  { label: "COLA FAQs", href: "https://www.ttb.gov/faqs/colas-and-formulas-online-faqs" },
  { label: "Distilled Spirits Checklist", href: "https://www.ttb.gov/system/files/images/labeling-ds/ds-labeling-checklist.pdf" },
  { label: "Beer Checklist", href: "https://www.ttb.gov/system/files/images/beer/labeling/malt-beverage-labeling-checklist-information.pdf" },
  { label: "Wine Checklist", href: "https://www.ttb.gov/system/files/images/wine-label/wine-labeling-checklist.pdf" },
];

function ResourcesPanel() {
  return (
    <aside className="resources">
      <h2>Resources</h2>
      <ul>
        {RESOURCES.map((r) => (
          <li key={r.href}>
            <a href={r.href} target="_blank" rel="noopener noreferrer">
              {r.label}
            </a>
          </li>
        ))}
      </ul>
    </aside>
  );
}

export default function App() {
  const [mode, setMode] = useState("single");

  return (
    <div className="app">
      <header>
        <h1>TTB Label Pre-Screen</h1>
      </header>

      <ResourcesPanel />

      <nav className="tabs">
        <button
          className={mode === "single" ? "tab active" : "tab"}
          onClick={() => setMode("single")}
        >
          Single Label
        </button>
        <button
          className={mode === "batch" ? "tab active" : "tab"}
          onClick={() => setMode("batch")}
        >
          Batch Upload
        </button>
      </nav>

      {mode === "single" ? <SingleVerifyForm /> : <BatchVerifyForm />}
    </div>
  );
}

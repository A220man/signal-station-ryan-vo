import React, { useState } from "react";
import { api, getCurrentRole } from "../api/client";
import { PatchResult } from "../types";

export const PatchStudio: React.FC = () => {
  const [filePath, setFilePath] = useState("example.py");
  const [originalSnippet, setOriginalSnippet] = useState("def add(a, b):\n  return a + b\n");
  const [modifiedSnippet, setModifiedSnippet] = useState("def add(a, b):\n    '''Add two numbers.'''\n    return a + b\n");
  const [toleranceMode, setToleranceMode] = useState<"exact" | "normalized_whitespace" | "fuzzy_hunk">("normalized_whitespace");
  const [result, setResult] = useState<PatchResult | null>(null);
  const [loading, setLoading] = useState(false);

  const role = getCurrentRole();
  const canOperate = role === "operator" || role === "admin";

  const handleApply = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canOperate) return;

    setLoading(true);
    try {
      const res = await api.applyPatch(filePath, originalSnippet, modifiedSnippet, toleranceMode);
      setResult(res);
    } catch (err: any) {
      alert(`Patch error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card patch-studio-container">
      <div className="section-header">
        <h2>Whitespace-Tolerant Patch Studio</h2>
        <p className="section-hint">
          Resolves agent edit tool failures caused by line break mismatches (CRLF vs LF) and indentation variations (tabs vs 2/4 spaces).
        </p>
      </div>

      <form onSubmit={handleApply} className="patch-form">
        <div className="form-row">
          <div className="form-group flex-1">
            <label>Target Workspace File Path</label>
            <input
              type="text"
              value={filePath}
              onChange={(e) => setFilePath(e.target.value)}
              placeholder="e.g., example.py"
            />
          </div>

          <div className="form-group flex-1">
            <label>Tolerance Mode</label>
            <select
              value={toleranceMode}
              onChange={(e) => setToleranceMode(e.target.value as any)}
            >
              <option value="normalized_whitespace">Normalized Whitespace (Recommended)</option>
              <option value="fuzzy_hunk">Fuzzy Hunk Alignment (&gt;= 0.85 ratio)</option>
              <option value="exact">Strict Exact Match</option>
            </select>
          </div>
        </div>

        <div className="form-row code-split">
          <div className="form-group flex-1">
            <label>Original Code Snippet (Target)</label>
            <textarea
              rows={8}
              className="code-textarea font-mono"
              value={originalSnippet}
              onChange={(e) => setOriginalSnippet(e.target.value)}
              placeholder="Snippet to find and replace..."
            />
          </div>

          <div className="form-group flex-1">
            <label>Replacement Code Snippet</label>
            <textarea
              rows={8}
              className="code-textarea font-mono"
              value={modifiedSnippet}
              onChange={(e) => setModifiedSnippet(e.target.value)}
              placeholder="New modified snippet..."
            />
          </div>
        </div>

        {canOperate ? (
          <button type="submit" className="btn btn-primary" disabled={loading}>
            {loading ? "Applying Patch..." : "Apply Resilient Patch"}
          </button>
        ) : (
          <div className="info-banner">Viewer role active: patch application requires Operator privileges.</div>
        )}
      </form>

      {result && (
        <div className={`patch-result-box ${result.success ? "success" : "failure"}`}>
          <div className="result-status-line">
            <strong>Status:</strong> {result.success ? "Patch Applied Successfully" : "Patch Application Failed"}
            <span className="strategy-tag">Strategy: {result.strategyApplied}</span>
          </div>
          <div className="result-msg">{result.message}</div>
          {result.diffPreview && (
            <div className="diff-view">
              <h4>Unified Diff Preview</h4>
              <pre className="font-mono">{result.diffPreview}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  );
};

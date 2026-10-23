import React from "react";
import { UserRole } from "../types";

interface NavbarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentRole: UserRole;
  onOpenAuth: () => void;
}

export const Navbar: React.FC<NavbarProps> = ({
  activeTab,
  setActiveTab,
  currentRole,
  onOpenAuth
}) => {
  const tabs = [
    { id: "dashboard", label: "Sessions & Goals" },
    { id: "patch", label: "Patch Resilience" },
    { id: "sandbox", label: "Safety Sandbox" },
    { id: "compaction", label: "Event Compaction" },
    { id: "benchmark", label: "AI/ML Benchmark" },
    { id: "fleet", label: "Agent Fleet" }
  ];

  return (
    <header className="navbar">
      <div className="navbar-brand">
        <span className="brand-logo">📡</span>
        <div className="brand-text">
          <h1>Signal Station</h1>
          <span className="brand-tag">Coding Agent Orchestrator</span>
        </div>
      </div>

      <nav className="navbar-nav">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            className={`nav-link ${activeTab === tab.id ? "active" : ""}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
          </button>
        ))}
      </nav>

      <div className="navbar-actions">
        <div className="badge-demo">
          <span className="dot online"></span>
          <span>Local Demo</span>
        </div>
        <button className="role-badge" onClick={onOpenAuth} title="Click to switch role">
          Role: <strong>{currentRole}</strong>
        </button>
      </div>
    </header>
  );
};

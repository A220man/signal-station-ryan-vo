import React, { useState } from "react";
import { UserRole } from "./types";
import { getCurrentRole } from "./api/client";
import { Navbar } from "./components/Navbar";
import { Dashboard } from "./components/Dashboard";
import { SessionDetail } from "./components/SessionDetail";
import { PatchStudio } from "./components/PatchStudio";
import { SandboxInspector } from "./components/SandboxInspector";
import { CompactionManager } from "./components/CompactionManager";
import { BenchmarkRunner } from "./components/BenchmarkRunner";
import { AuthModal } from "./components/AuthModal";
import "./App.css";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>("dashboard");
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null);
  const [currentRole, setCurrentRole] = useState<UserRole>(getCurrentRole());
  const [isAuthOpen, setIsAuthOpen] = useState(false);

  const handleSelectSession = (id: string) => {
    setSelectedSessionId(id);
  };

  const handleBackToSessions = () => {
    setSelectedSessionId(null);
  };

  const handleRoleChanged = (newRole: UserRole) => {
    setCurrentRole(newRole);
  };

  return (
    <div className="app-shell">
      <Navbar
        activeTab={activeTab}
        setActiveTab={(tab) => {
          setActiveTab(tab);
          setSelectedSessionId(null);
        }}
        currentRole={currentRole}
        onOpenAuth={() => setIsAuthOpen(true)}
      />

      <main className="main-content">
        {activeTab === "dashboard" && (
          selectedSessionId ? (
            <SessionDetail sessionId={selectedSessionId} onBack={handleBackToSessions} />
          ) : (
            <Dashboard onSelectSession={handleSelectSession} />
          )
        )}

        {activeTab === "patch" && <PatchStudio />}

        {activeTab === "sandbox" && <SandboxInspector />}

        {activeTab === "compaction" && <CompactionManager />}

        {activeTab === "benchmark" && <BenchmarkRunner />}
      </main>

      <footer className="app-footer">
        <div>Signal Station &bull; AI Coding Agent Orchestration & Sandboxing Platform</div>
        <div>Maintained by Ryan Vo &lt;ryandtvo@gmail.com&gt;</div>
      </footer>

      <AuthModal
        isOpen={isAuthOpen}
        onClose={() => setIsAuthOpen(false)}
        currentRole={currentRole}
        onRoleChanged={handleRoleChanged}
      />
    </div>
  );
};

export default App;

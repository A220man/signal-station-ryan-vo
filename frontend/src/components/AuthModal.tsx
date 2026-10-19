import React, { useState } from "react";
import { UserRole } from "../types";
import { api } from "../api/client";

interface AuthModalProps {
  isOpen: boolean;
  onClose: () => void;
  currentRole: UserRole;
  onRoleChanged: (role: UserRole) => void;
}

export const AuthModal: React.FC<AuthModalProps> = ({
  isOpen,
  onClose,
  currentRole,
  onRoleChanged
}) => {
  const [selectedRole, setSelectedRole] = useState<UserRole>(currentRole);
  const [loading, setLoading] = useState(false);

  if (!isOpen) return null;

  const handleSelectDemoRole = async (role: UserRole) => {
    setLoading(true);
    try {
      await api.loginDemo(`demo_${role}`, role);
      setSelectedRole(role);
      onRoleChanged(role);
      onClose();
    } catch (err: any) {
      alert(`Role switch error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-dialog auth-modal">
        <div className="modal-header">
          <h3>Authentication & Role Management</h3>
          <button className="modal-close" onClick={onClose}>
            &times;
          </button>
        </div>

        <div className="modal-body">
          <div className="auth-mode-badge">
            <span className="dot online"></span>
            <strong>Local Demo Mode Active (Development)</strong>
          </div>
          <p className="auth-hint">
            In development environments binding 127.0.0.1, you can switch between RBAC role contexts to inspect permissions.
          </p>

          <div className="role-selector-list">
            <div
              className={`role-option-card ${selectedRole === "viewer" ? "selected" : ""}`}
              onClick={() => handleSelectDemoRole("viewer")}
            >
              <div className="role-option-title">Viewer (Read-Only)</div>
              <div className="role-option-desc">Inspect sessions, read buffers, view metrics and compaction statistics. Cannot mutate state or dispatch tool calls.</div>
            </div>

            <div
              className={`role-option-card ${selectedRole === "operator" ? "selected" : ""}`}
              onClick={() => handleSelectDemoRole("operator")}
            >
              <div className="role-option-title">Operator (Standard Developer)</div>
              <div className="role-option-desc">Create agent sessions, set/pause/complete persistent /goal records, dispatch sandboxed tool steps, and apply whitespace patches.</div>
            </div>

            <div
              className={`role-option-card ${selectedRole === "admin" ? "selected" : ""}`}
              onClick={() => handleSelectDemoRole("admin")}
            >
              <div className="role-option-title">Admin (System Administrator)</div>
              <div className="role-option-desc">Full operator capabilities plus triggering SQLite event store compaction and snapshot pruning.</div>
            </div>
          </div>

          <hr className="divider" />
          <div className="sso-info">
            <h4>Keycloak SSO & Enterprise SAML</h4>
            <p>
              In production mode, authentication is governed by Keycloak via standard OIDC authorization code flow with PKCE (S256). Enterprise SAML IdPs are brokered transparently through Keycloak realm brokering.
            </p>
          </div>
        </div>

        <div className="modal-footer">
          <button className="btn btn-secondary" onClick={onClose} disabled={loading}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};

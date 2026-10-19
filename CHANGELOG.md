# Changelog

## 1.0.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

All notable changes to Signal Station will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.0.0] - 2026-10-18

### Added
- Core agent session orchestration engine with persistent `/goal` tracking, token and time budgeting, and post-execution verification checks.
- Safety sandbox and command risk policy engine enforcing directory containment and classifying shell operations (safe, guarded, prohibited).
- Whitespace-tolerant code patch engine with exact matching, indentation normalization, and fuzzy hunk fallback for LLM edit resilience.
- SQLite event store compaction engine pruning superseded snapshot events (`message.updated`, `state.updated`) and reducing disk bloat.
- AI/ML coding agent evaluation benchmark suite with deterministic offline scoring of safety policies, edit resilience, and goal precision.
- FastAPI backend with SQLite persistence, transactional mutations, audit logging, OIDC Keycloak authentication support with PKCE, and local demo mode.
- React 19 + TypeScript + Vite frontend dashboard with interactive session controls, live buffer search, patch tester, compaction manager, and benchmark runner.
- Docker and Docker Compose environment with non-root security contexts, healthchecks, and Keycloak realm import.
- GitHub Actions CI workflow for backend test coverage, frontend typecheck/tests, and container builds.

# Changelog

## 1.3.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

## 1.2.1 — work-in-progress checkpoint

### Fixed
- Database connection handling for in-memory SQLite in tests - services no longer close shared in-memory connections
- Added `is_in_memory_db()` helper to `backend/app/core/database.py` for consistent connection lifecycle management
- Fixed `steal_work` in `fleet_service.py` to re-fetch and return updated work items with correct `assigned_worker_id`
- Fixed test fixture in `test_work_queue.py` to not close in-memory connections
- Fixed test capacity in `test_migrate_session_work` to match expected behavior

### Verified
- All 54 backend tests pass
- All 7 frontend tests pass

## 1.2.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

## 1.1.0 — work-in-progress checkpoint

Partial code published for continued development. Known issues: STATUS.md.

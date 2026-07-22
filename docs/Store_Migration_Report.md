# Store Migration Report

## Scope and method

This is a read-only migration analysis of the repository as of 2026-07-22. The inventory covers:

- calls to `Store.get()`, `Store.put()`, and `Store.delete()` through a `Store` instance;
- `objects(kind=...)`-style reads, including the project's equivalent `Store.all(kind)` calls and direct SQL reads of `objects` filtered by `kind`;
- production code, tests, and historical Alembic data migrations.

Method definitions inside `backend/app/models/store.py` are not counted as usages. Calls to the newer relational repositories are also outside the inventory. File references are repository-relative and include the call/filter line.

### Summary

| Area | Exact `get` | Exact `put` | Exact `delete` | Kind-filtered enumeration / SQL read | Status |
|---|---:|---:|---:|---:|---|
| Production application | 5 | 6 | 0 | 2 | Correction, Comment, Export, and Idempotency still depend on the compatibility store |
| Tests | 2 | 3 | 0 | 1 | Directly tests compatibility-store behavior |
| Historical migrations | 0 | 0 | 0 | 6 | One-time legacy reads already feeding relational tables |
| **Total** | **7** | **9** | **0** | **9** | **25 usages inventoried** |

No source usage was found for Authentication, File, OCR Job, Page, or Result. Those application paths already use relational repositories. Their only remaining `objects` references are legacy reads in Alembic migrations.

Priority meanings: **High** = blocks removal of the compatibility store or affects correctness/concurrency; **Medium** = should migrate after core mutable records; **Low** = historical/test-only or can follow the production migration.

## Authentication

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/migrations/versions/622436c321e7_migrate_authentication_to_relational_.py:71` | `upgrade()` | `user` | get (legacy SQL kind-filtered read) | Existing `UserRepository` / `users` table | Low | Historical backfill must remain rerunnable; JSON field coercion, duplicate identities, tenant assignment, and timestamps can differ from relational constraints. Do not rewrite unless the migration chain itself is being retired. |
| `backend/migrations/versions/622436c321e7_migrate_authentication_to_relational_.py:98` | `upgrade()` | `session` | get (legacy SQL kind-filtered read) | Existing `SessionRepository` / `sessions` table | Low | Orphaned user references and revoked/expired-session interpretation can cause dropped or incorrectly active sessions. Preserve idempotent conflict handling. |

There are no production `Store.get/put/delete/all` calls in Authentication.

## File

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/migrations/versions/3670a613f7e1_migrate_files_and_jobs_to_relational_.py:82` | `upgrade()` | `file` | get (legacy SQL kind-filtered read) | Existing `FileRepository` / `files` table | Low | Owner/tenant joins can omit orphaned rows; legacy MIME, size, object path, soft-delete, and status fields must map without changing file visibility. |
| `backend/tests/test_store.py:11` | `test_store_upserts_and_separates_object_kinds()` | `file` | put | Existing `FileRepository` | Low | Test fixture lacks fields required by the relational schema; replace with a repository-specific fixture only when retiring `Store`. |
| `backend/tests/test_store.py:18` | `test_store_upserts_and_separates_object_kinds()` | `file` | get | Existing `FileRepository` | Low | This assertion tests cross-kind key separation, which relational tables provide structurally rather than through a composite `(kind, id)` key. |

There are no production application calls to the compatibility store in File.

## OCR Job

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/migrations/versions/3670a613f7e1_migrate_files_and_jobs_to_relational_.py:127` | `upgrade()` | `job` | get (legacy SQL kind-filtered read) | Existing `OCRJobRepository` / `ocr_jobs` table | Low | Jobs with missing users/files may be omitted by joins; JSON counters, page IDs, status, and timestamps require consistent defaults. |
| `backend/tests/test_store.py:10` | `test_store_upserts_and_separates_object_kinds()` | `job` | put | Existing `OCRJobRepository` | Low | Minimal test data does not satisfy relational foreign keys or required job fields. |
| `backend/tests/test_store.py:12` | `test_store_upserts_and_separates_object_kinds()` | `job` | put | Existing `OCRJobRepository` | Low | The test relies on generic upsert semantics; the repository currently exposes `create` but no general job update/upsert method. |
| `backend/tests/test_store.py:14` | `test_store_upserts_and_separates_object_kinds()` | `job` | get | Existing `OCRJobRepository` | Low | Replacing this test requires deciding whether duplicate creation should update, conflict, or use a dedicated state-transition method. |
| `backend/tests/test_store.py:22` | `test_store_upserts_and_separates_object_kinds()` | `job` | get (equivalent `Store.all`) | Existing `OCRJobRepository.all()` | Low | Ordering is unspecified in both implementations; assertions should not accidentally impose ordering during migration. |

There are no production application calls to the compatibility store in OCR Job.

## Page

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/migrations/versions/444de64a7889_migrate_ocr_pages_and_results.py:68` | `upgrade()` | `page` | get (legacy SQL kind-filtered read) | Existing `PageRepository` / `pages` table | Low | Pages whose job is missing are excluded; nested image JSON, result ordering, counts, and nullable error data must survive conversion. |

There are no production `Store.get/put/delete/all` calls in Page.

## Result

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/migrations/versions/444de64a7889_migrate_ocr_pages_and_results.py:102` | `upgrade()` | `result` | get (legacy SQL kind-filtered read) | Existing `OCRResultRepository` / `results` table | Low | Job/page joins may discard orphans; bbox must remain `[x1,y1,x2,y2]`; numeric score/confidence precision, polygon JSON, revision, and embedded current correction must be preserved. |

There are no production `Store.get/put/delete/all` calls in Result.

## Correction

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/app/services/core.py:483` | `MockOcrService.add_correction()` | `correction` | put | New `CorrectionRepository` backed by a normalized `corrections` table | High | Correction insert and result revision update currently occur in separate transactions, allowing partial writes. Migration should make revision checking, correction creation, and current-result update atomic and enforce uniqueness on `(result_id, revision)`. |
| `backend/app/api/routes.py:350` | `corrections()` | `correction` | get (equivalent `Store.all`) | New `CorrectionRepository.list_by_result(result_id)` | High | Current code scans all tenants' corrections then filters in memory. Repository filtering must enforce result ownership/tenant scope, stable revision ordering, and existing response semantics. |

## Comment

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/app/services/core.py:430` | `MockOcrService.comments()` | `comment` | get (equivalent `Store.all`) | New `CommentRepository.list_by_result(result_id)` | High | Global scan currently filters soft-deleted records in memory. SQL filtering must preserve ascending `created_at` order, soft-delete behavior, tenant isolation, and comment counts. |
| `backend/app/services/core.py:505` | `MockOcrService.add_comment()` | `comment` | put | New `CommentRepository.create()` | High | Author is embedded JSON today. A relational design needs stable author display semantics, foreign keys, tenant ownership, and an atomic/consistent count after insert. |
| `backend/app/api/routes.py:400` | `update_comment()` | `comment` | get | New `CommentRepository.get_for_result(comment_id, result_id)` | High | Fetch and authorization checks must not expose cross-result or cross-tenant existence; preserve 403 versus 404 behavior intentionally. |
| `backend/app/api/routes.py:409` | `update_comment()` | `comment` | put | New `CommentRepository.update_content()` | High | Read-modify-write has no concurrency guard. A repository should avoid lost updates and preserve `updated_at` formatting. |
| `backend/app/api/routes.py:426` | `delete_comment()` | `comment` | get | New `CommentRepository.get_for_result(comment_id, result_id)` | High | Same authorization and tenant-boundary risks as update; already-deleted behavior should be explicitly tested. |
| `backend/app/api/routes.py:433` | `delete_comment()` | `comment` | put (soft delete) | New `CommentRepository.soft_delete()` | High | Although the API operation is delete, storage uses `put`; preserve soft deletion, auditability, idempotency expectations, and comment-count changes. |

No `Store.delete()` call exists; comment deletion is implemented as a `get` followed by a soft-delete `put`.

## Export

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/app/services/core.py:550` | `MockOcrService.export()` | `export` | put | New `ExportRepository.create()` backed by an `exports` table | Medium | Workbook creation and metadata persistence are not atomic. A failed DB insert can orphan a file, while a failed file save produces no status record; storage paths and job/tenant ownership need explicit constraints. |
| `backend/app/api/routes.py:459` | `get_export()` | `export` | get | New `ExportRepository.get_for_job(export_id, job_id)` | Medium | Repository lookup must bind export to job and tenant without changing 404 behavior or response fields. |
| `backend/app/api/routes.py:475` | `download()` | `export` | get | New `ExportRepository.get_for_job(export_id, job_id)` | Medium | Metadata may exist while the `.xlsx` file is absent. Migration should define missing-file/status behavior and prevent path or tenant mismatches. |

## Idempotency

| File | Function/Class | Store key | Operation | Suggested Repository | Migration priority | Potential migration risk |
|---|---|---|---|---|---|---|
| `backend/app/api/routes.py:331` | `correct()` | `idempotency` | get | New `IdempotencyRepository.get(scope, key)` backed by an `idempotency_records` table | High | Cache keys include actor, result, and a caller-supplied key but have no expiry or request fingerprint. Concurrent requests can both miss and create duplicate corrections. |
| `backend/app/api/routes.py:337` | `correct()` | `idempotency` | put | New `IdempotencyRepository.put_if_absent()` in the same transaction as correction creation | High | A crash between correction creation and cache write breaks replay safety. Enforce a unique scoped key, store request fingerprint/response, define TTL, and commit atomically with the correction. |

## Other

No additional application, test, or migration usages were found outside the modules above. In particular:

- `Store.delete()` has no implementation and no call sites.
- No literal Python call shaped as `objects(kind=...)` exists.
- `backend/app/models/store.py` defines the generic `objects` table and `Store` methods but is infrastructure, not a usage site.
- Mentions in `backend/README.md` are documentation, not executable usages.

## Recommended migration order

1. **Correction and Idempotency together**: they share the strongest atomicity and concurrency dependency.
2. **Comment**: high-volume mutable data with authorization, tenant isolation, ordering, and soft-delete concerns.
3. **Export**: metadata is simpler, but database/file lifecycle consistency needs a defined policy.
4. **Compatibility-store tests and infrastructure**: update or remove only after all production callers are migrated.
5. **Historical migration reads**: normally retain unchanged so existing upgrade paths continue to work; remove only under a separately planned migration-baseline reset.

For every new repository, preserve the existing REST interfaces and response shapes, add repository/service/API tests, and update migration documentation as required by the project rules.

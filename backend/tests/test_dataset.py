import json
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import select, update

from app.models.schema import dataset_reviews, ocr_jobs
from app.services.dataset import normalized_points
from app.services.dataset_files import DatasetFiles
from tests.test_api import client, workflow, get_first_result, register_headers


def current_results(api, job, headers):
    return api.get(f"/api/v1/ocr/jobs/{job}/pages/1/results", headers=headers).json()["data"]["items"]


def complete(api, job, headers, items=None):
    items = current_results(api, job, headers) if items is None else items
    return api.post(f"/api/v1/ocr/jobs/{job}/review-completion", headers=headers, json={"expected_results": [
        {"id": r["id"], "revision": r["revision"], "geometry_revision": r["geometry_revision"], "review_status": r["review_status"]} for r in items
    ]})


def status(api, job, headers):
    return api.post("/api/v1/ocr/jobs/dataset-statuses", headers=headers, json={"job_ids": [job]}).json()["data"][0]


def save(api, job, headers, version):
    return api.post(f"/api/v1/ocr/jobs/{job}/dataset-entries", headers=headers, json={"reviewed_version": version})


def test_review_save_reedit_and_rebuild(tmp_path):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        assert status(api, job, headers)["state"] == "unreviewed"
        assert save(api, job, headers, 0).status_code == 409
        reviewed = complete(api, job, headers)
        assert reviewed.status_code == 200, reviewed.text
        value = reviewed.json()["data"]
        assert value["state"] == "reviewed"
        version = value["reviewed_version"]
        assert save(api, job, headers, version).json()["data"]["state"] == "saved"
        root = tmp_path / "incremental_ocr_dataset"
        image_id = value["image_id"]
        record = json.loads((root / "records" / f"{image_id}.json").read_text(encoding="utf-8"))
        assert len(record["annotations"]) == 3
        assert len((root / "Label.txt").read_text(encoding="utf-8").splitlines()) == 1
        assert len((root / "rec_gt.txt").read_text(encoding="utf-8").splitlines()) == 3
        original = (root / "rec_gt.txt").read_bytes()
        assert save(api, job, headers, version).status_code == 200
        assert (root / "rec_gt.txt").read_bytes() == original
        result = get_first_result(api, job, headers)
        corrected = api.post(f"/api/v1/ocr/results/{result['id']}/corrections", headers=headers, json={"corrected_text": "K111B2", "base_revision": result["revision"]})
        assert corrected.status_code == 201
        assert status(api, job, headers)["state"] == "unreviewed"
        assert save(api, job, headers, version).status_code == 409
        items = current_results(api, job, headers)
        api.post("/api/v1/ocr/results/review-status", headers=headers, json={"result_ids": [items[-1]["id"]], "review_status": "deleted"})
        reviewed = complete(api, job, headers).json()["data"]
        assert reviewed["image_id"] == image_id
        assert save(api, job, headers, reviewed["reviewed_version"]).status_code == 200
        assert not (root / "crop_img" / f"{image_id}_crop_2.jpg").exists()
        labels = (root / "rec_gt.txt").read_text(encoding="utf-8")
        assert "\tK111B2\n" in labels
        assert len(labels.splitlines()) == 2
        DatasetFiles(tmp_path).rebuild()
        assert (root / "rec_gt.txt").read_text(encoding="utf-8") == labels


def test_stale_review_and_ownership(tmp_path):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        items = current_results(api, job, headers)
        api.post("/api/v1/ocr/results/review-status", headers=headers, json={"result_ids": [items[0]["id"]], "review_status": "false_positive"})
        assert complete(api, job, headers, items).status_code == 409
        other = register_headers(api, "13800138000", "QC-OTHER")
        assert complete(api, job, other, []).status_code in {403, 404}
        assert save(api, job, other, 0).status_code in {403, 404}
        assert api.post("/api/v1/ocr/jobs/dataset-statuses", headers=other, json={"job_ids": [job]}).status_code == 404


@pytest.mark.parametrize("text", ["", "   ", "###", "X\tY", "X\nY"])
def test_invalid_transcription_blocks_review(tmp_path, text):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        item = get_first_result(api, job, headers)
        api.post(f"/api/v1/ocr/results/{item['id']}/corrections", headers=headers, json={"corrected_text": text, "base_revision": 0})
        assert complete(api, job, headers).status_code == 422
        assert status(api, job, headers)["state"] == "unreviewed"


def test_empty_annotations_and_comments_do_not_invalidate(tmp_path):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        items = current_results(api, job, headers)
        api.post("/api/v1/ocr/results/review-status", headers=headers, json={"result_ids": [r["id"] for r in items], "review_status": "false_positive"})
        reviewed = complete(api, job, headers).json()["data"]
        api.post(f"/api/v1/ocr/results/{items[0]['id']}/comments", headers=headers, json={"content": "已经核对"})
        assert status(api, job, headers)["state"] == "reviewed"
        assert save(api, job, headers, reviewed["reviewed_version"]).status_code == 200
        root = tmp_path / "incremental_ocr_dataset"
        assert (root / "rec_gt.txt").read_bytes() == b""
        assert (root / "Label.txt").read_text().endswith("\t[]\n")
        assert list((root / "crop_img").iterdir()) == []


def test_failed_publication_preserves_previous_and_retries(tmp_path, monkeypatch):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        first = complete(api, job, headers).json()["data"]
        assert save(api, job, headers, first["reviewed_version"]).status_code == 200
        root = tmp_path / "incremental_ocr_dataset"
        previous = (root / "rec_gt.txt").read_bytes()
        item = get_first_result(api, job, headers)
        api.post(f"/api/v1/ocr/results/{item['id']}/corrections", headers=headers, json={"corrected_text": "NEW", "base_revision": 0})
        second = complete(api, job, headers).json()["data"]
        build = DatasetFiles.build_labels
        def fail(*args):
            raise OSError("injected disk error")
        monkeypatch.setattr(DatasetFiles, "build_labels", fail)
        assert save(api, job, headers, second["reviewed_version"]).status_code == 503
        assert (root / "rec_gt.txt").read_bytes() == previous
        assert status(api, job, headers)["state"] == "failed"
        monkeypatch.setattr(DatasetFiles, "build_labels", build)
        assert save(api, job, headers, second["reviewed_version"]).json()["data"]["state"] == "saved"
        assert b"\tNEW\n" in (root / "rec_gt.txt").read_bytes()


def test_parallel_retries_publish_once(tmp_path):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        reviewed = complete(api, job, headers).json()["data"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: save(api, job, headers, reviewed["reviewed_version"]), range(2)))
        assert all(response.status_code == 200 for response in responses)
        assert len(list((tmp_path / "incremental_ocr_dataset" / "records").glob("*.json"))) == 1


def test_edit_during_publication_does_not_mark_new_version_saved(tmp_path, monkeypatch):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        reviewed = complete(api, job, headers).json()["data"]
        publish = DatasetFiles.publish
        def editing_publish(files, *args):
            publish(files, *args)
            with api.app.state.service.store.engine.begin() as db:
                db.execute(update(ocr_jobs).where(ocr_jobs.c.id == job).values(result_version=ocr_jobs.c.result_version + 1))
        monkeypatch.setattr(DatasetFiles, "publish", editing_publish)
        response = save(api, job, headers, reviewed["reviewed_version"])
        assert response.json()["data"]["state"] == "unreviewed"


def test_points_preserve_perspective_and_reject_bowtie():
    assert normalized_points([[10, 10], [80, 12], [78, 30], [12, 28]], None, 100, 100) == [[10, 10], [80, 12], [78, 30], [12, 28]]
    from fastapi import HTTPException
    with pytest.raises(HTTPException):
        normalized_points([[0, 0], [10, 10], [10, 0], [0, 10]], None, 100, 100)
    with pytest.raises(HTTPException):
        normalized_points([[0, 0], [0.1, 0], [0.1, 0.1], [0, 0.1]], None, 100, 100)


def test_roi_can_be_reviewed_and_duplicate_image_conflicts(tmp_path):
    from tests.ocr_fakes import wait_for_job
    with client(tmp_path) as api:
        job, headers = workflow(api)
        original = complete(api, job, headers).json()["data"]
        roi = api.post("/api/v1/ocr/region-jobs", headers=headers, json={
            "name": "ROI", "source_job_id": job, "model_id": "mock", "model_version": "1.0.0",
            "pages": [{"page_no": 1, "regions": [{"client_id": "a", "bbox": [100, 100, 600, 400]}]}],
        }).json()["data"]["id"]
        wait_for_job(api, roi, headers)
        reviewed = complete(api, roi, headers)
        assert reviewed.status_code == 200, reviewed.text
        assert reviewed.json()["data"]["image_id"] == original["image_id"]
        assert save(api, job, headers, original["reviewed_version"]).status_code == 200
        assert save(api, roi, headers, reviewed.json()["data"]["reviewed_version"]).status_code == 409
        again = complete(api, roi, headers).json()["data"]
        assert save(api, roi, headers, again["reviewed_version"]).status_code == 200
        assert status(api, job, headers)["state"] == "unreviewed"


def test_geometry_create_delete_invalidate_and_align_crop_indices(tmp_path):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        complete(api, job, headers)
        item = get_first_result(api, job, headers)
        body = {"updates": [{"result_id": item["id"], "bbox": [10, 10, 100, 50], "polygon": [[10, 10], [100, 12], [98, 50], [12, 48]], "base_revision": 0}], "creates": [{"client_id": "manual", "bbox": [200, 200, 400, 250], "text": "MANUAL"}], "deletes": []}
        edited = api.post(f"/api/v1/ocr/jobs/{job}/pages/1/result-edits", headers=headers, json=body)
        assert edited.status_code == 200, edited.text
        assert status(api, job, headers)["state"] == "unreviewed"
        reviewed = complete(api, job, headers).json()["data"]
        manual_id = edited.json()["data"]["created"][0]["id"]
        deleted = api.post(f"/api/v1/ocr/jobs/{job}/pages/1/result-edits", headers=headers, json={"deletes": [{"result_id": manual_id}]})
        assert deleted.status_code == 200
        assert save(api, job, headers, reviewed["reviewed_version"]).status_code == 409
        reviewed = complete(api, job, headers).json()["data"]
        assert save(api, job, headers, reviewed["reviewed_version"]).status_code == 200
        root = tmp_path / "incremental_ocr_dataset"
        record = json.loads(next((root / "records").glob("*.json")).read_text(encoding="utf-8"))
        lines = (root / "rec_gt.txt").read_text(encoding="utf-8").splitlines()
        for i, annotation in enumerate(record["annotations"]):
            path, text = lines[i].split("\t")
            assert path.endswith(f"_crop_{i}.jpg") and (root / path).exists()
            assert text == annotation["transcription"]
        assert record["annotations"][0]["points"] == body["updates"][0]["polygon"]


def test_idempotency_key_payload_conflict(tmp_path):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        reviewed = complete(api, job, headers).json()["data"]
        keyed = {**headers, "Idempotency-Key": "save-once"}
        first = save(api, job, keyed, reviewed["reviewed_version"])
        assert first.status_code == 200
        assert save(api, job, keyed, reviewed["reviewed_version"]).json()["data"] == first.json()["data"]
        assert save(api, job, keyed, reviewed["reviewed_version"] + 1).status_code == 409


def test_commit_recovery_after_acknowledgement_failure(tmp_path, monkeypatch):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        reviewed = complete(api, job, headers).json()["data"]
        publish = DatasetFiles.publish
        def fail_after_commit(files, *args):
            publish(files, *args)
            raise OSError("process interruption before DB acknowledgement")
        monkeypatch.setattr(DatasetFiles, "publish", fail_after_commit)
        assert save(api, job, headers, reviewed["reviewed_version"]).status_code == 503
        monkeypatch.setattr(DatasetFiles, "publish", lambda *args: pytest.fail("Already committed data must not be republished"))
        assert save(api, job, headers, reviewed["reviewed_version"]).json()["data"]["state"] == "saved"


def test_new_migration_up_and_down(tmp_path):
    import importlib.util
    from pathlib import Path
    from sqlalchemy import create_engine, inspect
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    path = Path(__file__).parents[1] / "migrations/versions/d903_dataset_review.py"
    spec = importlib.util.spec_from_file_location("dataset_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    engine = create_engine(f"sqlite:///{tmp_path / 'migration.db'}")
    with engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE ocr_jobs (id VARCHAR(36) PRIMARY KEY)")
        connection.exec_driver_sql("INSERT INTO ocr_jobs (id) VALUES ('old-task')")
        with Operations.context(MigrationContext.configure(connection)):
            migration.upgrade()
            assert connection.exec_driver_sql("SELECT result_version FROM ocr_jobs").scalar() == 0
            assert {"dataset_images", "dataset_reviews"} <= set(inspect(connection).get_table_names())
            migration.downgrade()
            assert connection.exec_driver_sql("SELECT id FROM ocr_jobs").scalar() == "old-task"
            assert "dataset_reviews" not in inspect(connection).get_table_names()
    engine.dispose()


def test_publication_does_not_rename_directories(tmp_path, monkeypatch):
    from pathlib import Path
    def deny_rename(*args, **kwargs):
        raise PermissionError("Windows directory rename denied")
    with client(tmp_path) as api:
        job, headers = workflow(api)
        reviewed = complete(api, job, headers).json()["data"]
        monkeypatch.setattr(Path, "rename", deny_rename)
        assert save(api, job, headers, reviewed["reviewed_version"]).status_code == 200
        assert (tmp_path / "incremental_ocr_dataset/Label.txt").exists()


def test_partial_file_publication_rolls_back(tmp_path, monkeypatch):
    with client(tmp_path) as api:
        job, headers = workflow(api)
        reviewed = complete(api, job, headers).json()["data"]
        assert save(api, job, headers, reviewed["reviewed_version"]).status_code == 200
        root = tmp_path / "incremental_ocr_dataset"
        before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
        item = get_first_result(api, job, headers)
        api.post(f"/api/v1/ocr/results/{item['id']}/corrections", headers=headers, json={"corrected_text": "NEW", "base_revision": 0})
        reviewed = complete(api, job, headers).json()["data"]
        mirror = DatasetFiles.mirror
        def partial(files, source, destination):
            if source == files.stage:
                (destination / "Label.txt").write_text("partial update", encoding="utf-8")
                raise OSError("injected file replacement failure")
            return mirror(files, source, destination)
        monkeypatch.setattr(DatasetFiles, "mirror", partial)
        assert save(api, job, headers, reviewed["reviewed_version"]).status_code == 503
        assert {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()} == before
        assert not (tmp_path / ".dataset-transaction.json").exists()


def test_interrupted_transaction_recovers_before_next_operation(tmp_path):
    import shutil
    files = DatasetFiles(tmp_path)
    files.root.mkdir()
    (files.root / "Label.txt").write_text("old", encoding="utf-8")
    shutil.copytree(files.root, files.backup)
    files.transaction_state("applying", True)
    (files.root / "Label.txt").write_text("partial", encoding="utf-8")
    with files.locked():
        assert (files.root / "Label.txt").read_text(encoding="utf-8") == "old"
        assert not files.journal.exists()

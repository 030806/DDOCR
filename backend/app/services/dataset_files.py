"""Serialized, recoverable publication of complete training directories."""
from contextlib import contextmanager
import csv
import json
import os
from pathlib import Path
import shutil
import threading
import time

import cv2
import numpy as np
from PIL import Image

_mutex = threading.Lock()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")


class DatasetFiles:
    def __init__(self, parent: Path):
        self.parent = parent.resolve()
        self.root = self.parent / "incremental_ocr_dataset"
        self.stage = self.parent / ".dataset-stage"
        self.backup = self.parent / ".dataset-backup"
        self.journal = self.parent / ".dataset-transaction.json"

    @staticmethod
    def retry_file_operation(operation):
        for attempt in range(5):
            try:
                return operation()
            except PermissionError:
                if attempt == 4:
                    raise
                time.sleep(0.05 * 2 ** attempt)

    def mirror(self, source, destination):
        """Replace files under an existing directory, never rename directories.

        All callers hold the dataset lock. The publication marker is replaced
        last; an interrupted update is rolled back from the journal on entry.
        """
        destination.mkdir(parents=True, exist_ok=True)
        for directory in source.rglob("*"):
            if directory.is_dir():
                (destination / directory.relative_to(source)).mkdir(parents=True, exist_ok=True)
        source_files = {path.relative_to(source): path for path in source.rglob("*") if path.is_file()}
        for relative in sorted(source_files, key=lambda p: (p.name == ".publication.json", str(p))):
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(target.name + ".dataset-write")
            shutil.copyfile(source_files[relative], temporary)
            self.retry_file_operation(lambda: os.replace(temporary, target))
        for path in destination.rglob("*"):
            if path.is_file() and path.relative_to(destination) not in source_files:
                self.retry_file_operation(path.unlink)

    def transaction_state(self, state, had_root):
        temporary = self.journal.with_suffix(".tmp")
        write_json(temporary, {"state": state, "had_root": had_root})
        self.retry_file_operation(lambda: os.replace(temporary, self.journal))

    def recover(self):
        if self.journal.exists():
            transaction = json.loads(self.journal.read_text(encoding="utf-8"))
            if transaction["state"] == "applying":
                if transaction["had_root"]:
                    if not self.backup.exists():
                        raise OSError("Dataset rollback copy is missing")
                    self.mirror(self.backup, self.root)
                else:
                    self.remove(self.root)
            self.journal.unlink()
        elif not self.root.exists() and self.backup.exists():
            # Recover an interruption from the previous directory-swap format.
            self.mirror(self.backup, self.root)
        self.remove(self.backup)
        self.remove(self.stage)

    def remove(self, path):
        if path.resolve().parent != self.parent or path.is_symlink():
            raise ValueError("Unsafe dataset work directory")
        if path.exists():
            shutil.rmtree(path)

    @contextmanager
    def locked(self):
        # The OS lock is released even after process termination. All publishers
        # on a deployment must share this directory and a filesystem with locks.
        with _mutex, (self.parent / ".dataset.lock").open("a+b") as lock:
            lock.seek(0, 2)
            if not lock.tell():
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_LOCK, 1)
            else:
                import fcntl
                fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                self.recover()
                yield
            finally:
                lock.seek(0)
                if os.name == "nt":
                    msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(lock, fcntl.LOCK_UN)

    def publication(self):
        path = self.root / ".publication.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    def build_labels(self, root):
        """Regenerate every derived file from original images and records."""
        crops = root / "crop_img"
        if crops.exists():
            shutil.rmtree(crops)
        crops.mkdir()
        labels, recognition, states, manifest = [], [], [], []
        import hashlib
        for record_path in sorted((root / "records").glob("*.json")):
            record = json.loads(record_path.read_text(encoding="utf-8"))
            image_id = record["image_id"]
            image_paths = list((root / "images").glob(f"{image_id}.*"))
            if len(image_paths) != 1:
                raise ValueError("Dataset image missing or ambiguous")
            path = image_paths[0]
            with Image.open(path) as opened:
                image = np.array(opened.convert("RGB"))
            if (image.shape[1], image.shape[0]) != (record["image_width"], record["image_height"]):
                raise ValueError("Dataset image size mismatch")
            annotations = record["annotations"]
            for index, annotation in enumerate(annotations):
                points = np.array(annotation["points"], dtype=np.float32)
                width = max(2, round(max(np.linalg.norm(points[1]-points[0]), np.linalg.norm(points[2]-points[3]))))
                height = max(2, round(max(np.linalg.norm(points[3]-points[0]), np.linalg.norm(points[2]-points[1]))))
                target = np.array([[0, 0], [width-1, 0], [width-1, height-1], [0, height-1]], dtype=np.float32)
                crop = cv2.warpPerspective(image, cv2.getPerspectiveTransform(points, target), (width, height))
                crop_path = f"crop_img/{image_id}_crop_{index}.jpg"
                Image.fromarray(crop).save(root / crop_path, quality=95)
                recognition.append(f"{crop_path}\t{annotation['transcription']}\n")
            relative = f"images/{path.name}"
            detection = [{"transcription": a["transcription"], "points": a["points"], "difficult": False} for a in annotations]
            labels.append(relative + "\t" + json.dumps(detection, ensure_ascii=False, separators=(",", ":")) + "\n")
            states.append(relative + "\t1\n")
            manifest.append([image_id, record["original_filename"], relative, hashlib.sha256(path.read_bytes()).hexdigest(), record["image_width"], record["image_height"], record["confirmed_at"]])
        for name, lines in [("Label.txt", labels), ("rec_gt.txt", recognition), ("fileState.txt", states)]:
            (root / name).write_text("".join(lines), encoding="utf-8", newline="\n")
        with (root / "image_manifest.csv").open("w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream)
            writer.writerow(["image_id", "original_filename", "dataset_path", "sha256", "width", "height", "confirmed_at"])
            writer.writerows(manifest)

    def prepare(self):
        if self.root.exists():
            shutil.copytree(self.root, self.stage)
        else:
            (self.stage / "images").mkdir(parents=True)
            (self.stage / "records").mkdir()

    def commit(self):
        # Windows watchers/ACLs can prohibit renaming nonempty directories even
        # when their files are writable. Keep the directory stable and journal
        # file replacements, with a complete rollback copy under the same lock.
        had_root = self.root.exists()
        if had_root:
            shutil.copytree(self.root, self.backup)
        self.transaction_state("applying", had_root)
        try:
            self.mirror(self.stage, self.root)
            self.transaction_state("committed", had_root)
        except BaseException:
            # Keep the journal and backup if rollback itself fails, so the next
            # locked operation must recover before any publication is attempted.
            self.recover()
            raise
        # Publication is complete. Delayed cleanup must not turn success into a
        # failed save; recover() retries cleanup before the next operation.
        try:
            self.recover()
        except OSError:
            pass

    def publish(self, record, content, extension, metadata):
        self.prepare()
        image_id = record["image_id"]
        for path in (self.stage / "images").glob(f"{image_id}.*"):
            path.unlink()
        (self.stage / "images" / f"{image_id}.{extension}").write_bytes(content)
        write_json(self.stage / "records" / f"{image_id}.json", record)
        publication = self.publication()
        publication[image_id] = metadata
        write_json(self.stage / ".publication.json", publication)
        self.build_labels(self.stage)
        self.commit()

    def rebuild(self):
        with self.locked():
            self.prepare()
            self.build_labels(self.stage)
            self.commit()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Rebuild OCR training labels under a DDOCR data directory")
    parser.add_argument("data_dir", type=Path)
    DatasetFiles(parser.parse_args().data_dir).rebuild()

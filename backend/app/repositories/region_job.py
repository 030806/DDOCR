"""Persistence for independent region OCR job scopes."""

from typing import Any

from sqlalchemy import Engine, insert, select
from sqlalchemy.orm import Session

from app.models.schema import ocr_job_regions, ocr_region_job_scopes


class RegionJobRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create(
        self,
        *,
        job_id: str,
        source_job_id: str | None,
        file_id: str,
        created_by: str,
        regions: list[dict[str, Any]],
    ) -> None:
        with Session(self.engine) as db, db.begin():
            db.execute(insert(ocr_region_job_scopes).values(
                job_id=job_id,
                source_job_id=source_job_id,
                file_id=file_id,
                region_count=len(regions),
                created_by=created_by,
            ))
            db.execute(insert(ocr_job_regions), regions)

    def context(self, job_id: str) -> dict[str, Any] | None:
        with Session(self.engine) as db:
            scope = db.execute(
                select(ocr_region_job_scopes).where(ocr_region_job_scopes.c.job_id == job_id)
            ).first()
            if not scope:
                return None
            rows = db.execute(
                select(ocr_job_regions)
                .where(ocr_job_regions.c.job_id == job_id)
                .order_by(ocr_job_regions.c.page_no, ocr_job_regions.c.reading_order)
            ).all()
            regions = [
                {
                    "id": row._mapping["id"],
                    "client_id": row._mapping["client_id"],
                    "page_no": row._mapping["page_no"],
                    "bbox": list(row._mapping["bbox"]),
                    "reading_order": row._mapping["reading_order"],
                }
                for row in rows
            ]
            mapping = scope._mapping
            return {
                "job_id": job_id,
                "source_job_id": mapping["source_job_id"],
                "file_id": mapping["file_id"],
                "region_count": mapping["region_count"],
                "regions": regions,
            }

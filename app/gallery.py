"""Build and idempotently ingest request-model-compatible LFW vector bundles."""

import argparse
import base64
import binascii
import gzip
import json
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from fastapi import HTTPException
from sqlalchemy import case, func
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.config import get_settings
from app.db import SessionLocal
from app.face_provider import FaceNotFoundError, get_face_provider
from app.images import normalize_image_bytes
from app.matching import validated_embedding
from app.models import Celebrity, FaceSample

FORMAT_VERSION = 2
SUPPORTED_FORMAT_VERSIONS = {1, FORMAT_VERSION}
LFW_NOTICE = "LFW image license not stated; reviewed noncommercial PoC use required"
MAX_PORTRAIT_BYTES = 1_000_000


def identity_id(label: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"double-trouble:lfw:identity:{label}"))


def sample_id(relative_path: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"double-trouble:lfw:sample:{relative_path}"))


def build_bundle(lfw_dir: Path, output_path: Path, acknowledgement: bool, include_portraits: bool) -> None:
    if not acknowledgement:
        raise SystemExit("Pass --acknowledge-lfw-rights-review after reviewing LFW provenance and intended use.")
    settings = get_settings()
    provider = get_face_provider()
    image_paths = sorted(path for path in lfw_dir.glob("*/*") if path.suffix.casefold() in {".jpg", ".jpeg", ".png"})
    if not image_paths:
        raise SystemExit(f"No labeled images found below {lfw_dir}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_suffix(output_path.suffix + ".part")
    written = 0
    rejected = 0
    portrait_labels: set[str] = set()
    with gzip.open(temporary, "wt", encoding="utf-8", newline="\n") as bundle:
        manifest = {
            "type": "manifest",
            "format_version": FORMAT_VERSION,
            "created_at": datetime.now(UTC).isoformat(),
            "source_dataset": "LFW",
            "source_notice": LFW_NOTICE,
            "model_version": settings.face_model_version,
            "embedding_dim": settings.face_embedding_dim,
            "portraits_included": include_portraits,
        }
        bundle.write(json.dumps(manifest, separators=(",", ":")) + "\n")
        for image_path in image_paths:
            relative_path = image_path.relative_to(lfw_dir).as_posix()
            label = image_path.parent.name
            try:
                normalized = normalize_image_bytes(image_path.read_bytes(), settings.max_image_pixels, settings.image_max_side)
                embedding = validated_embedding(provider.embed(normalized), settings.face_embedding_dim)
            except (FaceNotFoundError, HTTPException, ValueError):
                rejected += 1
                continue
            record = {
                "type": "sample",
                "id": sample_id(relative_path),
                "celebrity_id": identity_id(label),
                "display_name": label.replace("_", " "),
                "source_dataset": "LFW",
                "source_image_id": relative_path,
                "source_license": LFW_NOTICE,
                "embedding": embedding,
            }
            if include_portraits and label not in portrait_labels:
                portrait = normalize_image_bytes(
                    normalized,
                    settings.max_image_pixels,
                    min(512, settings.retained_image_max_side),
                    quality=82,
                )
                record["portrait_jpeg_b64"] = base64.b64encode(portrait).decode("ascii")
                portrait_labels.add(label)
            bundle.write(json.dumps(record, separators=(",", ":")) + "\n")
            written += 1
    temporary.replace(output_path)
    if written == 0:
        output_path.unlink(missing_ok=True)
        raise SystemExit("No usable faces were embedded; check the detector, model files, and dataset layout.")
    digest = sha256(output_path.read_bytes()).hexdigest()
    print(f"bundle={output_path} samples={written} rejected={rejected} sha256={digest}")


def ingest_bundle(bundle_path: Path) -> None:
    settings = get_settings()
    celebrities: dict[str, dict] = {}
    samples: list[dict] = []
    with gzip.open(bundle_path, "rt", encoding="utf-8") as bundle:
        manifest = json.loads(next(bundle))
        if manifest.get("type") != "manifest" or manifest.get("format_version") not in SUPPORTED_FORMAT_VERSIONS:
            raise SystemExit("Unsupported gallery bundle format")
        if manifest.get("embedding_dim") != settings.face_embedding_dim:
            raise SystemExit("Gallery embedding dimension does not match the application")
        if manifest.get("model_version") != settings.face_model_version:
            raise SystemExit("Gallery model version does not match FACE_MODEL_VERSION")
        for line in bundle:
            record = json.loads(line)
            if record.get("type") != "sample":
                raise SystemExit("Unexpected gallery bundle record")
            embedding = validated_embedding(record["embedding"], settings.face_embedding_dim)
            celebrity_id = record["celebrity_id"]
            celebrity = celebrities.setdefault(
                celebrity_id,
                {
                    "id": celebrity_id,
                    "display_name": record["display_name"],
                    "candidate_type": "gallery",
                    "portrait_image": None,
                    "portrait_media_type": None,
                    "is_hot_or_not_active": False,
                },
            )
            portrait_value = record.get("portrait_jpeg_b64")
            if portrait_value:
                try:
                    portrait = base64.b64decode(portrait_value, validate=True)
                except (binascii.Error, ValueError) as exc:
                    raise SystemExit("Gallery portrait is not valid base64") from exc
                if not portrait or len(portrait) > MAX_PORTRAIT_BYTES:
                    raise SystemExit("Gallery portrait is empty or exceeds the size limit")
                celebrity["portrait_image"] = portrait
                celebrity["portrait_media_type"] = "image/jpeg"
                celebrity["is_hot_or_not_active"] = True
            samples.append({
                "id": record["id"],
                "celebrity_id": celebrity_id,
                "source_dataset": record["source_dataset"],
                "source_image_id": record["source_image_id"],
                "source_url": None,
                "source_license": record["source_license"],
                "embedding": list(embedding),
            })
    with SessionLocal.begin() as db:
        celebrity_insert = pg_insert(Celebrity).values(list(celebrities.values()))
        db.execute(celebrity_insert.on_conflict_do_update(
            index_elements=[Celebrity.id],
            set_={
                "display_name": celebrity_insert.excluded.display_name,
                "candidate_type": "gallery",
                "portrait_image": func.coalesce(
                    celebrity_insert.excluded.portrait_image,
                    Celebrity.portrait_image,
                ),
                "portrait_media_type": func.coalesce(
                    celebrity_insert.excluded.portrait_media_type,
                    Celebrity.portrait_media_type,
                ),
                "is_hot_or_not_active": case(
                    (celebrity_insert.excluded.portrait_image.is_not(None), True),
                    else_=Celebrity.is_hot_or_not_active,
                ),
            },
        ))
        for offset in range(0, len(samples), 250):
            sample_insert = pg_insert(FaceSample).values(samples[offset:offset + 250])
            db.execute(sample_insert.on_conflict_do_update(
                index_elements=[FaceSample.id],
                set_={
                    "celebrity_id": sample_insert.excluded.celebrity_id,
                    "source_dataset": sample_insert.excluded.source_dataset,
                    "source_image_id": sample_insert.excluded.source_image_id,
                    "source_license": sample_insert.excluded.source_license,
                    "embedding": sample_insert.excluded.embedding,
                },
            ))
    print(f"ingested identities={len(celebrities)} samples={len(samples)} model={settings.face_model_version}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    build = subparsers.add_parser("build", help="create a compressed vector bundle from labeled LFW directories")
    build.add_argument("--lfw-dir", type=Path, required=True)
    build.add_argument("--output", type=Path, required=True)
    build.add_argument("--acknowledge-lfw-rights-review", action="store_true")
    build.add_argument(
        "--include-portraits",
        action="store_true",
        help="include one display portrait per identity after explicit rights review",
    )
    ingest = subparsers.add_parser("ingest", help="idempotently load a vector bundle into DATABASE_URL")
    ingest.add_argument("--bundle", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "build":
        build_bundle(
            args.lfw_dir,
            args.output,
            args.acknowledge_lfw_rights_review,
            args.include_portraits,
        )
    else:
        ingest_bundle(args.bundle)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

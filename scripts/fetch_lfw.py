
import argparse
import csv
import hashlib
import tarfile
from pathlib import Path

import httpx

URL = "https://ndownloader.figshare.com/files/5976015"
EXPECTED_SHA256 = (
    "b47c8422c8cded889dc5a13418c4bc2a"
    "bbda121092b3533a83306f90d900100a"
)


def checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(archive: Path) -> None:
    if archive.exists() and checksum(archive) == EXPECTED_SHA256:
        print("Using existing verified archive")
        return

    temporary = archive.with_suffix(".tgz.part")

    try:
        with httpx.stream(
            "GET",
            URL,
            follow_redirects=True,
            timeout=httpx.Timeout(120.0, connect=30.0),
        ) as response:
            response.raise_for_status()

            with temporary.open("wb") as output:
                for chunk in response.iter_bytes(1024 * 1024):
                    output.write(chunk)

        if checksum(temporary) != EXPECTED_SHA256:
            raise RuntimeError("LFW archive checksum mismatch")

        temporary.replace(archive)

    finally:
        temporary.unlink(missing_ok=True)


def extract(archive: Path, destination: Path) -> Path:
    root = destination / "lfw_funneled"

    if root.is_dir() and any(root.rglob("*.jpg")):
        return root

    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            path = Path(member.name)

            if (
                path.is_absolute()
                or ".." in path.parts
                or not path.parts
                or path.parts[0] != "lfw_funneled"
                or not (member.isfile() or member.isdir())
            ):
                raise RuntimeError(
                    f"Unsafe archive member: {member.name}"
                )

        bundle.extractall(destination, filter="data")

    return root


def build_manifest(root: Path, destination: Path) -> None:
    manifest = destination / "lfw_manifest.csv"
    count = 0
    identities = set()

    with manifest.open("w", newline="", encoding="utf-8") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=[
                "image_path",
                "identity_id",
                "person_name",
                "source_dataset",
            ],
        )
        writer.writeheader()

        for image in sorted(root.glob("*/*.jpg")):
            identity = image.parent.name
            identities.add(identity)

            writer.writerow({
                "image_path": str(image.relative_to(destination)),
                "identity_id": identity,
                "person_name": identity.replace("_", " "),
                "source_dataset": "lfw_funneled",
            })
            count += 1

    print(f"Indexed {count} images, {len(identities)} identities")
    print(f"Manifest: {manifest}")


def fetch(destination: Path, acknowledgement: bool) -> None:
    if not acknowledgement:
        raise SystemExit(
            "Pass --acknowledge-unclear-lfw-rights "
            "after reviewing the LFW provenance and intended use."
        )

    destination.mkdir(parents=True, exist_ok=True)

    archive = destination / "lfw-funneled.tgz"
    download(archive)
    root = extract(archive, destination)
    build_manifest(root, destination)

    print(f"Dataset ready: {root}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Download and index LFW-funneled"
    )
    parser.add_argument(
        "--destination",
        type=Path,
        required=True,
    )
    parser.add_argument(
        "--acknowledge-unclear-lfw-rights",
        action="store_true",
    )
    args = parser.parse_args()

    fetch(args.destination, args.acknowledge_unclear_lfw_rights)

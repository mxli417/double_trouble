import argparse
from hashlib import sha256
from pathlib import Path

import httpx

MODELS = {
    "face_detection_yunet_2023mar.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
    ),
    "face_recognition_sface_2021dec.onnx": (
        "https://github.com/opencv/opencv_zoo/raw/main/models/face_recognition_sface/face_recognition_sface_2021dec.onnx",
        "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79",
    ),
}


def fetch(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, (url, expected_hash) in MODELS.items():
        destination = output_dir / filename
        if destination.is_file() and sha256(destination.read_bytes()).hexdigest() == expected_hash:
            continue
        temporary = destination.with_suffix(destination.suffix + ".part")
        digest = sha256()
        with httpx.stream("GET", url, follow_redirects=True, timeout=120) as response, temporary.open("wb") as output:
            response.raise_for_status()
            for chunk in response.iter_bytes(1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        if digest.hexdigest() != expected_hash:
            temporary.unlink(missing_ok=True)
            raise RuntimeError(f"Checksum mismatch for {filename}")
        temporary.replace(destination)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch checksum-pinned OpenCV YuNet and SFace models")
    parser.add_argument("--output", type=Path, required=True)
    fetch(parser.parse_args().output)

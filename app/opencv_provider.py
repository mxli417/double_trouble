from pathlib import Path
from threading import Lock

import cv2
import numpy as np

from app.config import Settings
from app.face_provider import FaceNotFoundError


class OpenCVFaceProvider:
    def __init__(self, settings: Settings):
        model_dir = Path(settings.face_model_path or "")
        detector_path = model_dir / "face_detection_yunet_2023mar.onnx"
        recognizer_path = model_dir / "face_recognition_sface_2021dec.onnx"
        if not detector_path.is_file() or not recognizer_path.is_file():
            raise RuntimeError("OpenCV face model files are missing")
        self.detector = cv2.FaceDetectorYN.create(
            str(detector_path),
            "",
            (320, 320),
            settings.face_detection_score_threshold,
            settings.face_detection_nms_threshold,
            5000,
        )
        self.recognizer = cv2.FaceRecognizerSF.create(str(recognizer_path), "")
        self.embedding_dim = settings.face_embedding_dim
        self.min_face_size = settings.face_min_size
        self.lock = Lock()

    def embed(self, image_bytes: bytes) -> tuple[float, ...]:
        encoded = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(encoded, cv2.IMREAD_COLOR)
        if image is None:
            raise FaceNotFoundError("Image could not be decoded for face detection")
        height, width = image.shape[:2]
        with self.lock:
            self.detector.setInputSize((width, height))
            _, faces = self.detector.detect(image)
            if faces is None or len(faces) == 0:
                raise FaceNotFoundError("No face was detected")
            face = max(faces, key=lambda candidate: self._selection_score(candidate, width, height))
            if min(float(face[2]), float(face[3])) < self.min_face_size:
                raise FaceNotFoundError("The selected face is too small")
            aligned = self.recognizer.alignCrop(image, face)
            feature = self.recognizer.feature(aligned).reshape(-1).astype(np.float32)
        norm = float(np.linalg.norm(feature))
        if norm == 0 or feature.size != self.embedding_dim:
            raise RuntimeError("OpenCV face recognizer returned an invalid embedding")
        return tuple(float(value) for value in feature / norm)

    @staticmethod
    def _selection_score(face: np.ndarray, width: int, height: int) -> float:
        x, y, face_width, face_height = (float(value) for value in face[:4])
        center_x = x + face_width / 2
        center_y = y + face_height / 2
        distance = ((center_x - width / 2) / width) ** 2 + ((center_y - height / 2) / height) ** 2
        confidence = float(face[-1])
        return face_width * face_height * confidence / (1.0 + distance)


def create_provider(settings: Settings) -> OpenCVFaceProvider:
    return OpenCVFaceProvider(settings)

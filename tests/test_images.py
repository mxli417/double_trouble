import unittest
from io import BytesIO

from fastapi import HTTPException
from PIL import Image

from app.images import normalize_image_bytes
from app.opencv_provider import OpenCVFaceProvider


class ImagePipelineTests(unittest.TestCase):
    @staticmethod
    def jpeg(width=640, height=480):
        output = BytesIO()
        Image.new("RGB", (width, height), "white").save(output, "JPEG")
        return output.getvalue()

    def test_normalization_bounds_long_side_and_emits_rgb_jpeg(self):
        normalized = normalize_image_bytes(self.jpeg(1200, 600), max_pixels=1_000_000, max_side=300)
        with Image.open(BytesIO(normalized)) as image:
            self.assertEqual(image.format, "JPEG")
            self.assertEqual(image.mode, "RGB")
            self.assertEqual(image.size, (300, 150))

    def test_normalization_rejects_pixel_bomb_before_decode(self):
        with self.assertRaises(HTTPException) as raised:
            normalize_image_bytes(self.jpeg(100, 100), max_pixels=9_999, max_side=300)
        self.assertEqual(raised.exception.status_code, 413)

    def test_face_selection_prefers_large_centered_candidate(self):
        centered = [100, 80, 120, 120, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.9]
        edge = [0, 0, 80, 80, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0.99]
        self.assertGreater(
            OpenCVFaceProvider._selection_score(centered, 320, 280),
            OpenCVFaceProvider._selection_score(edge, 320, 280),
        )


if __name__ == "__main__":
    unittest.main()

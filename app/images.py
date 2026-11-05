from io import BytesIO

from fastapi import HTTPException
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

register_heif_opener()

ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


def normalize_image_bytes(image_bytes: bytes, max_pixels: int, max_side: int, quality: int = 92) -> bytes:
    try:
        with Image.open(BytesIO(image_bytes)) as source:
            if source.width * source.height > max_pixels:
                raise HTTPException(status_code=413, detail="Image dimensions are too large")
            source.load()
            image = ImageOps.exif_transpose(source).convert("RGB")
            image.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
            output = BytesIO()
            image.save(output, format="JPEG", quality=quality, optimize=True)
            return output.getvalue()
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise HTTPException(status_code=415, detail="Image could not be decoded") from exc

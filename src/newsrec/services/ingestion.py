from io import BytesIO
import warnings

from PIL import Image, ImageOps, UnidentifiedImageError

MAX_BYTES = 50 * 1024 * 1024
MAX_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS


def ingest(content: bytes) -> tuple[bytes, bytes]:
    if not content or len(content) > MAX_BYTES:
        raise ValueError("upload must contain 1 byte to 50 MiB")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(content)) as probe:
                if probe.width * probe.height > MAX_PIXELS:
                    raise ValueError("image exceeds 50 megapixels")
                if getattr(probe, "n_frames", 1) != 1:
                    raise ValueError("only single-page images are supported")
                probe.verify()
            with Image.open(BytesIO(content)) as source:
                image = ImageOps.exif_transpose(source).convert("RGB")
                full, thumb = BytesIO(), BytesIO()
                image.save(full, format="PNG")
                image.thumbnail((800, 800))
                image.save(thumb, format="PNG")
                return full.getvalue(), thumb.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("invalid or oversized image") from exc

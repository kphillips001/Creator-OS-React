"""Original-resolution selective Gaussian blur rendering from a durable mask."""

from pathlib import Path
from tempfile import NamedTemporaryFile
import os

from PIL import Image, ImageFilter, ImageOps, UnidentifiedImageError


class SelectiveBlurService:
    MAX_SOURCE_PIXELS = 50_000_000
    MAX_MASK_DIMENSION = 2048

    def render(self, *, source_path, mask_path, output_path, blur_strength: int):
        strength = int(blur_strength)
        if not 1 <= strength <= 80:
            raise ValueError("Blur strength must be between 1 and 80.")
        source_path, mask_path, output_path = map(Path, (source_path, mask_path, output_path))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(source_path) as opened:
                original = ImageOps.exif_transpose(opened).convert("RGB")
            if original.width * original.height > self.MAX_SOURCE_PIXELS:
                raise ValueError("Source image dimensions exceed the selective blur safety limit.")
            with Image.open(mask_path) as opened_mask:
                if max(opened_mask.size) > self.MAX_MASK_DIMENSION:
                    raise ValueError("Mask dimensions exceed the selective blur safety limit.")
                mask = opened_mask.getchannel("A") if "A" in opened_mask.getbands() else opened_mask.convert("L")
                mask = mask.resize(original.size, Image.Resampling.LANCZOS)
            blurred = original.filter(ImageFilter.GaussianBlur(radius=strength))
            result = Image.composite(blurred, original, mask)
        except (UnidentifiedImageError, OSError) as error:
            raise ValueError("Original image or selective blur mask is corrupt or unsupported.") from error
        suffix = output_path.suffix or ".png"
        with NamedTemporaryFile(dir=output_path.parent, suffix=suffix, delete=False) as temp:
            temporary = Path(temp.name)
        try:
            result.save(temporary, format="PNG", optimize=True)
            os.replace(temporary, output_path)
        finally:
            temporary.unlink(missing_ok=True)
        return output_path

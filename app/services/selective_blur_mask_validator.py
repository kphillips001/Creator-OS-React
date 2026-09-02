"""Domain-neutral validation for operator-authored selective-blur PNG masks."""
import base64
from io import BytesIO
from PIL import Image, UnidentifiedImageError


class SelectiveBlurMaskValidator:
    MASK_VERSION = "selective_blur_mask_v1"
    MAX_MASK_BYTES = 8 * 1024 * 1024

    def decode(self, value, width: int, height: int) -> bytes:
        width, height = int(width), int(height)
        if not 1 <= width <= 2048 or not 1 <= height <= 2048:
            raise ValueError("Mask dimensions must be between 1 and 2048 pixels.")
        try:
            encoded = str(value).split(",", 1)[1] if str(value).startswith("data:image/png;base64,") else str(value)
            raw = base64.b64decode(encoded, validate=True)
            if not raw or len(raw) > self.MAX_MASK_BYTES: raise ValueError
            with Image.open(BytesIO(raw)) as mask: mask.verify()
            with Image.open(BytesIO(raw)) as mask:
                if mask.size != (width, height): raise ValueError
                alpha = mask.getchannel("A") if "A" in mask.getbands() else mask.convert("L")
                if alpha.getbbox() is None:
                    raise ValueError("Selective blur mask must contain at least one painted blur region.")
        except (ValueError, OSError, UnidentifiedImageError, base64.binascii.Error) as error:
            if isinstance(error, ValueError) and "painted blur" in str(error): raise
            raise ValueError("Selective blur mask is invalid or corrupt.") from error
        return raw

    @staticmethod
    def is_full_blur(raw: bytes) -> bool:
        """Classify final mask coverage without trusting the editor's selected tool."""
        with Image.open(BytesIO(raw)) as mask:
            alpha = mask.getchannel("A") if "A" in mask.getbands() else mask.convert("L")
            minimum, maximum = alpha.getextrema()
            return minimum == 255 and maximum == 255

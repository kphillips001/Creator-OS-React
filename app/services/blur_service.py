from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

from app.services.local_vault_service import LocalVaultService
from app.services.runtime_media_resolver import RuntimeMediaResolver


_RUNTIME_MEDIA_RESOLVER = RuntimeMediaResolver()
FULL_BLUR_STRENGTH = 40


def _resolve_original_path(original_media: Any) -> Path | None:
    if isinstance(original_media, (str, Path)):
        return _RUNTIME_MEDIA_RESOLVER.resolve_original_path(
            {"file_path": str(original_media)},
            require_exists=True,
        )

    return _RUNTIME_MEDIA_RESOLVER.resolve_original_path(
        original_media,
        require_exists=True,
    )


def generate_blurred_preview(
    original_path: Any,
    blur_strength: int = FULL_BLUR_STRENGTH,
    overwrite: bool = False,
    output_dir: str | Path | None = None,
) -> str:
    """
    Takes an original image path and generates a blurred preview version.

    Args:
        original_path: Path string or Asset-like object for the original image
        blur_strength (int): Blur intensity (default = 40)
        overwrite (bool): Whether to regenerate if preview already exists
        output_dir: Optional derivative output directory

    Returns:
        str: blurred image path
    """

    original = _resolve_original_path(original_path)

    if not original:
        raise FileNotFoundError(f"Original file not found: {original_path}")

    preview_dir = (
        Path(output_dir)
        if output_dir is not None
        else LocalVaultService().path("vault/blurred")
    )
    preview_dir.mkdir(parents=True, exist_ok=True)

    # Create blurred filename
    blurred_filename = f"{original.stem}_blurred{original.suffix}"
    blurred_path = preview_dir / blurred_filename

    # 🚀 Skip if already exists (prevents duplicate work)
    if blurred_path.exists() and not overwrite:
        print(f"[BLUR SKIPPED] Already exists: {blurred_path}")
        return str(blurred_path)

    print(f"[BLUR START] Processing: {original_path}")

    # Open and blur image through the same renderer used by stateless previews.
    blurred = render_full_blur(original, blur_strength=blur_strength)
    try:
        blurred.save(blurred_path, quality=95)
    finally:
        blurred.close()

    print(f"[BLUR COMPLETE] Saved to: {blurred_path}")

    return str(blurred_path)


def render_full_blur(original_path: Any, *, blur_strength: int = FULL_BLUR_STRENGTH) -> Image.Image:
    """Return the canonical original-resolution FULL_BLUR image without persisting it."""
    original = _resolve_original_path(original_path)
    if not original:
        raise FileNotFoundError(f"Original file not found: {original_path}")
    with Image.open(original) as opened:
        normalized = ImageOps.exif_transpose(opened).convert("RGB")
    return normalized.filter(ImageFilter.GaussianBlur(radius=int(blur_strength)))

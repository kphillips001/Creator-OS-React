"""Standalone Creator utility for batch image metadata stripping."""

from __future__ import annotations

import io
import os
import tempfile
import zipfile
from pathlib import Path

import streamlit as st

from app.services.metadata_strip_service import MetadataStripService


OUTPUT_DIRECTORY = Path(r"D:\Strip MetaData")


def _download_all_bytes(paths: tuple[Path, ...]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in paths:
            if path.is_file():
                archive.write(path, arcname=path.name)
    return buffer.getvalue()


def render_strip_metadata(
    *,
    metadata_strip_service: MetadataStripService | None = None,
) -> None:
    service = metadata_strip_service or MetadataStripService()
    st.title("Strip Metadata")
    st.caption("Remove identifying metadata from images while preserving their format and dimensions.")

    st.markdown("### Drop Images Here")
    st.caption("or")
    uploads = st.file_uploader(
        "Upload Images",
        type=["jpg", "jpeg", "png", "webp"],
        accept_multiple_files=True,
        key="strip_metadata_uploads",
    )

    st.markdown("### Selected Files")
    if uploads:
        for upload in uploads:
            st.write(upload.name)
    else:
        st.caption("No images selected.")

    st.markdown("### Output Folder")
    st.code(str(OUTPUT_DIRECTORY), language="text")

    if st.button(
        "Strip Metadata",
        type="primary",
        disabled=not uploads,
        use_container_width=True,
    ):
        progress = st.progress(0, text="Processing...")
        completed = []
        errors = []
        total = len(uploads)
        for index, upload in enumerate(uploads, start=1):
            suffix = Path(upload.name).suffix.lower()
            staged = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            staged_path = Path(staged.name)
            try:
                staged.write(upload.getbuffer())
                staged.close()
                result = service.strip_to_path(
                    staged_path,
                    output_dir=OUTPUT_DIRECTORY,
                    preferred_filename=upload.name,
                )
                completed.append(Path(result.output_path))
            except Exception as exc:
                errors.append(f"{upload.name}: {exc}")
            finally:
                staged.close()
                staged_path.unlink(missing_ok=True)
            progress.progress(index / total, text=f"Processing {index} of {total}...")

        st.session_state["strip_metadata_completed_paths"] = tuple(
            str(path) for path in completed
        )
        st.session_state["strip_metadata_errors"] = tuple(errors)

    completed_paths = tuple(
        Path(path)
        for path in st.session_state.get("strip_metadata_completed_paths", ())
        if Path(path).is_file()
    )
    errors = st.session_state.get("strip_metadata_errors", ())
    if completed_paths:
        st.success("Completed")
        for path in completed_paths:
            st.write(f"✔ {path.name}")
        st.write("Saved to:")
        st.code(str(OUTPUT_DIRECTORY), language="text")

        st.markdown("### Metadata Removed")
        for label in (
            "EXIF",
            "IPTC",
            "XMP",
            "GPS",
            "Camera Metadata",
            "Software Metadata",
        ):
            st.write(f"✓ {label}")

        st.markdown("### Downloads")
        for path in completed_paths:
            st.download_button(
                f"Download {path.name}",
                data=path.read_bytes(),
                file_name=path.name,
                mime="application/octet-stream",
                key=f"strip_metadata_download_{path.name}",
            )
        st.download_button(
            "Download All",
            data=_download_all_bytes(completed_paths),
            file_name="stripped_metadata_images.zip",
            mime="application/zip",
            use_container_width=True,
        )
        if st.button("Open Output Folder", use_container_width=True):
            OUTPUT_DIRECTORY.mkdir(parents=True, exist_ok=True)
            os.startfile(str(OUTPUT_DIRECTORY))

    for error in errors:
        st.error(error)

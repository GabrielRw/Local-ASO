"""Read an image's type and pixel size from its header (PNG and JPEG), without decoding it."""

from __future__ import annotations

import struct

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SOF_MARKERS = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def image_info(data: bytes) -> tuple[str, int, int]:
    """Return ("png" | "jpeg", width, height), or raise ValueError for anything else."""

    if data.startswith(PNG_SIGNATURE) and len(data) >= 24 and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return "png", int(width), int(height)
    if data.startswith(b"\xff\xd8"):
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            (length,) = struct.unpack(">H", data[index + 2 : index + 4])
            if marker in _JPEG_SOF_MARKERS:
                height, width = struct.unpack(">HH", data[index + 5 : index + 9])
                return "jpeg", int(width), int(height)
            index += 2 + length
    raise ValueError("only PNG and JPEG images are supported")

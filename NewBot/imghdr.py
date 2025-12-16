"""Backport of the stdlib imghdr module (removed in Python 3.13+).

This minimal copy keeps the public API compatible for libraries (например,
python-telegram-bot 13.x) которые ожидают наличие imghdr.what().
"""

from __future__ import annotations

import binascii
from typing import BinaryIO, Callable, Iterable, Optional


def what(file: str, h: Optional[bytes] = None) -> Optional[str]:
    """Определить тип изображения по сигнатуре."""
    f: Optional[BinaryIO] = None
    try:
        if h is None:
            f = open(file, "rb")
            h = f.read(32)
        for test in tests:
            res = test(h, f)
            if res:
                return res
        return None
    finally:
        if f is not None:
            f.close()


def test_jpeg(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[6:10] in (b"JFIF", b"Exif"):
        return "jpeg"
    if h[:4] == b"\xff\xd8\xff\xdb":
        return "jpeg"
    if h[:4] == b"\xff\xd8\xff\xe0" and h[6:10] == b"JFIF":
        return "jpeg"
    return None


def test_png(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:8] == b"\211PNG\r\n\032\n":
        return "png"
    return None


def test_gif(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return None


def test_tiff(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:2] in (b"MM", b"II"):
        return "tiff"
    return None


def test_rgb(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:2] == b"\001\332":
        return "rgb"
    return None


def test_pbm(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if len(h) >= 3 and h[0:2] == b"P1":
        return "pbm"
    return None


def test_pgm(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if len(h) >= 3 and h[0:2] == b"P2":
        return "pgm"
    return None


def test_ppm(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if len(h) >= 3 and h[0:2] == b"P3":
        return "ppm"
    return None


def test_rast(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:4] == b"\x59\xA6\x6A\x95":
        return "rast"
    return None


def test_xbm(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:2] == b"#d":
        return "xbm"
    return None


def test_bmp(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:2] == b"BM":
        return "bmp"
    return None


def test_webp(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:4] == b"RIFF" and h[8:12] == b"WEBP":
        return "webp"
    return None


def test_exr(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
    if h[:4] == b"\x76\x2f\x31\x01":
        return "exr"
    return None


tests: Iterable[Callable[[bytes, Optional[BinaryIO]], Optional[str]]] = (
    test_jpeg,
    test_png,
    test_gif,
    test_tiff,
    test_rgb,
    test_pbm,
    test_pgm,
    test_ppm,
    test_rast,
    test_xbm,
    test_bmp,
    test_webp,
    test_exr,
)



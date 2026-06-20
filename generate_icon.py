"""KeyFlux 아이콘(.ico) 생성기.

main.py 의 _render_icon_pixmap 디자인(보라 라운드 사각형 + 흰 "K")을 그대로
여러 크기의 PNG 로 렌더해, 단일 멀티사이즈 .ico (PNG 프레임)로 묶는다.
이 .ico 는 PyInstaller 의 --icon 으로 전달되어 exe 파일/작업표시줄 아이콘
(파비콘)으로 쓰인다. (앱 실행 중 창/트레이 아이콘은 main.make_app_icon 이
같은 디자인을 코드로 렌더하므로 별도 파일 없이도 동일하게 보인다.)

실행:
    python generate_icon.py        -> keyflux.ico 생성
"""
import os
import struct

# 네이티브 플랫폼을 써서 시스템 폰트("Arial")로 "K" 글자가 정상 렌더되게
# 한다. (offscreen 플랫폼은 폰트가 없어 글자가 빈 사각형으로 찍힌다.)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QBuffer, QByteArray, QIODevice

import main  # _render_icon_pixmap 디자인 재사용 (단일 출처)

SIZES = [16, 24, 32, 48, 64, 128, 256]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "keyflux.ico")


def _png_bytes(size: int) -> bytes:
    pix = main._render_icon_pixmap(size)
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pix.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def _build_ico(frames) -> bytes:
    """frames: [(size, png_bytes)] -> ICO 바이너리.
    각 프레임을 PNG 그대로 담는다(Vista+ 지원). 256 크기는 폭/높이 필드를
    0 으로 표기하는 ICO 규약을 따른다."""
    count = len(frames)
    out = struct.pack("<HHH", 0, 1, count)  # reserved, type=1(icon), count
    offset = 6 + 16 * count
    images = b""
    for size, data in frames:
        dim = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32,
                           len(data), offset)
        images += data
        offset += len(data)
    return out + images


def main_gen():
    app = QApplication([])  # 참조 유지: GC 되면 C++ 앱이 파괴되어 렌더 실패
    frames = [(s, _png_bytes(s)) for s in SIZES]
    with open(OUT, "wb") as f:
        f.write(_build_ico(frames))
    print(f"Wrote {OUT} ({len(frames)} sizes)")


if __name__ == "__main__":
    main_gen()

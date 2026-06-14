import sys
import os
import json
import re
import time
import signal
import threading
import datetime
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QTableWidget, QTableWidgetItem, QLabel, QLineEdit,
    QDialog, QFormLayout, QComboBox, QMessageBox, QSystemTrayIcon,
    QMenu, QHeaderView, QFrame, QCheckBox, QFileDialog
)
from PyQt6.QtCore import Qt, pyqtSignal, QObject, QTimer, QSharedMemory
from PyQt6.QtGui import QIcon, QColor, QFont, QPixmap, QPainter
from pynput import keyboard
from pynput.keyboard import Key, Controller
import ctypes


# ── 유니코드 직접 주입 (Windows SendInput) ───────────────────────
# 치환 텍스트를 클립보드+Ctrl+V로 붙여넣지 않고, 글자를 "가상키"가 아닌
# "유니코드 코드포인트" 자체로 OS 입력 큐에 주입한다(KEYEVENTF_UNICODE).
#   - IME를 거치지 않으므로 한글 조합형/분리형 문제와 글자 순서 꼬임이 없음
#   - 클립보드를 건드리지 않으므로 사용자가 복사해둔 내용이 보존됨
#   - 붙여넣기 단축키(Ctrl+V/Ctrl+Shift+V)에 의존하지 않으므로
#     메모장·브라우저뿐 아니라 터미널(PowerShell/cmd/Git Bash 등)에서도
#     "그냥 타이핑한 글자"로 동일하게 들어간다.
if sys.platform == "win32":
    from ctypes import wintypes

    _PUL = ctypes.POINTER(ctypes.c_ulong)

    class _KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
            ("dwExtraInfo", _PUL),
        ]

    class _MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG), ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD), ("dwExtraInfo", _PUL),
        ]

    class _HARDWAREINPUT(ctypes.Structure):
        _fields_ = [
            ("uMsg", wintypes.DWORD),
            ("wParamL", wintypes.WORD), ("wParamH", wintypes.WORD),
        ]

    # INPUT 구조체의 union은 가장 큰 멤버(MOUSEINPUT) 크기를 가져야 하므로
    # ki 외에 mi/hi도 함께 정의해 sizeof(INPUT)가 OS 기대값과 일치하게 한다.
    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT)]

    class _INPUT(ctypes.Structure):
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    _INPUT_KEYBOARD = 1
    _KEYEVENTF_KEYUP = 0x0002
    _KEYEVENTF_UNICODE = 0x0004

    # 주의: ctypes.windll.user32.SendInput 은 pynput 등과 공유되는 캐시된
    # 함수 객체다. 여기에 .argtypes 를 박으면 pynput 의 SendInput 호출이
    # 타입 불일치로 깨진다(백스페이스/타이핑 전부 실패). 그래서 공유 객체를
    # 건드리지 않고, 우리 INPUT 구조체에 맞춘 "별도 함수 객체"를 만들어 쓴다.
    _SendInput = ctypes.WINFUNCTYPE(
        wintypes.UINT, wintypes.UINT, ctypes.POINTER(_INPUT), ctypes.c_int
    )(("SendInput", ctypes.windll.user32))

    def send_unicode_string(text: str) -> bool:
        """text를 KEYEVENTF_UNICODE로 한 번에 주입한다. 성공 시 True.
        BMP 밖 문자(이모지 등)는 UTF-16 서로게이트 2개로 자동 분할 전송된다.
        모든 키 이벤트를 단일 SendInput 호출로 보내 글자 순서를 OS가 보장한다."""
        if not text:
            return True
        codes = []
        for ch in text:
            b = ch.encode("utf-16-le")
            for i in range(0, len(b), 2):
                codes.append(b[i] | (b[i + 1] << 8))

        n = len(codes) * 2  # 글자당 keydown + keyup
        arr = (_INPUT * n)()
        idx = 0
        for code in codes:
            arr[idx].type = _INPUT_KEYBOARD
            arr[idx].u.ki = _KEYBDINPUT(0, code, _KEYEVENTF_UNICODE, 0, None)
            idx += 1
            arr[idx].type = _INPUT_KEYBOARD
            arr[idx].u.ki = _KEYBDINPUT(
                0, code, _KEYEVENTF_UNICODE | _KEYEVENTF_KEYUP, 0, None)
            idx += 1

        sent = _SendInput(n, arr, ctypes.sizeof(_INPUT))
        return sent == n

    # ── 스캔코드 키 이벤트 주입 (터미널 호환) ─────────────────────
    # KEYEVENTF_UNICODE 로 주입한 글자는 가상키 코드가 0이라, GUI 앱은
    # 받지만 PowerShell PSReadLine·cmd·readline 같은 "콘솔 줄 편집기"는
    # 흘려버린다(→ 터미널에서 단축어가 안 먹히는 원인).
    # 실제 키보드처럼 "스캔코드 키 이벤트"로 보내면 콘솔 줄 편집기도
    # 정상 인식한다. 단, 스캔코드는 키보드 레이아웃/IME 를 거치므로
    # 키보드로 칠 수 없는 글자(한글 등)는 보낼 수 없다 → 그런 글자만
    # 유니코드로 폴백한다(한글은 콘솔에선 제한적이나 GUI 에선 정상).
    _KEYEVENTF_SCANCODE = 0x0008
    _VK_SHIFT = 0x10
    _CTRL_OR_ALT = 0x06  # VkKeyScan 상위바이트의 Ctrl(2)|Alt(4) 비트
    # 공유 객체 오염 방지: argtypes 를 박지 않고 WINFUNCTYPE 로 별도 함수 생성
    _VkKeyScanW = ctypes.WINFUNCTYPE(wintypes.SHORT, wintypes.WCHAR)(
        ("VkKeyScanW", ctypes.windll.user32))
    _MapVirtualKeyW = ctypes.WINFUNCTYPE(wintypes.UINT, wintypes.UINT, wintypes.UINT)(
        ("MapVirtualKeyW", ctypes.windll.user32))
    _SPECIAL_VK = {"\n": 0x0D, "\t": 0x09}  # 줄바꿈/탭은 전용 가상키로

    def _send_key_inputs(events) -> bool:
        """events: (wVk, wScan, dwFlags) 리스트를 단일 SendInput 으로 전송."""
        n = len(events)
        arr = (_INPUT * n)()
        for i, (vk, sc, fl) in enumerate(events):
            arr[i].type = _INPUT_KEYBOARD
            arr[i].u.ki = _KEYBDINPUT(vk, sc, fl, 0, None)
        return _SendInput(n, arr, ctypes.sizeof(_INPUT)) == n

    def _char_key_events(ch: str):
        """한 글자를 스캔코드 키 이벤트 리스트로 변환.
        키보드로 칠 수 없는 글자면 None(→ 호출자가 유니코드로 폴백)."""
        if ch == "\r":
            return []
        if ch in _SPECIAL_VK:
            vk = _SPECIAL_VK[ch]
            sc = _MapVirtualKeyW(vk, 0)
            return [(vk, sc, _KEYEVENTF_SCANCODE),
                    (vk, sc, _KEYEVENTF_SCANCODE | _KEYEVENTF_KEYUP)]
        res = _VkKeyScanW(ch)
        if res == -1:
            return None
        vk = res & 0xFF
        shift_state = (res >> 8) & 0xFF
        if shift_state & _CTRL_OR_ALT:
            return None  # AltGr/Ctrl 조합 글자는 유니코드로
        sc = _MapVirtualKeyW(vk, 0)
        if sc == 0:
            return None
        evs = []
        sh_sc = _MapVirtualKeyW(_VK_SHIFT, 0)
        if shift_state & 1:
            evs.append((_VK_SHIFT, sh_sc, _KEYEVENTF_SCANCODE))
        evs.append((vk, sc, _KEYEVENTF_SCANCODE))
        evs.append((vk, sc, _KEYEVENTF_SCANCODE | _KEYEVENTF_KEYUP))
        if shift_state & 1:
            evs.append((_VK_SHIFT, sh_sc, _KEYEVENTF_SCANCODE | _KEYEVENTF_KEYUP))
        return evs

    def send_text(text: str, char_delay: float = 0.01) -> bool:
        """text 를 글자 단위로 주입. 칠 수 있는 글자는 스캔코드 키로,
        못 치는 글자는 유니코드로. GUI·터미널 모두에서 동작.
        콘솔 줄 편집기가 빠른 연속 입력을 흘리지 않도록 글자당 짧게 지연."""
        if not text:
            return True
        ok = True
        for ch in text:
            evs = _char_key_events(ch)
            if evs is None:
                if not send_unicode_string(ch):
                    ok = False
            elif evs:
                if not _send_key_inputs(evs):
                    ok = False
            time.sleep(char_delay)
        return ok
else:
    def send_unicode_string(text: str) -> bool:
        """비-Windows: 직접 주입 미지원. 호출자가 폴백 타이핑을 쓰도록 False 반환."""
        return False

    def send_text(text: str, char_delay: float = 0.01) -> bool:
        """비-Windows: 직접 주입 미지원. 호출자가 폴백 타이핑을 쓰도록 False 반환."""
        return False

# ── 데이터 저장 경로 ──────────────────────────────────────────────
# 우선순위: 실행파일/스크립트 옆 rules.json  >  홈디렉토리 fallback
def _resolve_data_file() -> Path:
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).parent   # PyInstaller exe 옆
    else:
        base = Path(__file__).parent         # 스크립트 옆
    candidate = base / "rules.json"
    if candidate.exists():
        return candidate
    return Path.home() / ".keyflux_rules.json"

DATA_FILE = _resolve_data_file()

# ── 기본 규칙 ────────────────────────────────────────────────────
DEFAULT_RULES = [
    {"type": "word",    "trigger": "abc",   "output": "123",    "enabled": True},
    {"type": "special", "trigger": ";date", "output": "{date}", "enabled": True},
    {"type": "special", "trigger": ";time", "output": "{time}", "enabled": True},
    {"type": "regex",   "trigger": r"\d{4}-\d{2}-\d{2}", "output": "[DATE]", "enabled": False},
]

# ── 규칙 저장/불러오기 ────────────────────────────────────────────
def load_rules():
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return DEFAULT_RULES[:]

def save_rules(rules):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(rules, f, ensure_ascii=False, indent=2)

# ── 출력 텍스트 처리 (특수 변수 치환) ────────────────────────────
# {date} {time} {datetime} 는 기본 형식을 그대로 사용하고,
# {date:형식} 처럼 콜론 뒤에 strftime 형식 코드를 직접 적으면
# 원하는 형식으로 출력할 수 있다.
#   {date:%Y%m%d}   -> 20260613
#   {date:%m-%d}    -> 06-13
#   {time:%H:%M}    -> 20:03
#   {datetime:%y%m%d_%H%M%S} -> 260613_200300
_PLACEHOLDER_RE = re.compile(r"\{(date|time|datetime)(?::([^{}]*))?\}")
_DEFAULT_DT_FORMATS = {
    "date": "%Y-%m-%d",
    "time": "%H:%M:%S",
    "datetime": "%Y-%m-%d %H:%M:%S",
}

def resolve_output(output: str) -> str:
    now = datetime.datetime.now()

    def _sub(m):
        kind = m.group(1)
        fmt = m.group(2) if m.group(2) else _DEFAULT_DT_FORMATS[kind]
        try:
            return now.strftime(fmt)
        except Exception:
            return m.group(0)  # 잘못된 형식이면 원본 그대로 남김

    return _PLACEHOLDER_RE.sub(_sub, output)


# ── 한글 자모 조합 (두벌식 오토마타) ─────────────────────────────
# Windows의 전역 키보드 후크는 한글을 "완성된 글자(조합형)"가 아니라
# "자모 단위(분리형)"로 전달한다 (예: "안" → ㅇ,ㅏ,ㄴ 3개의 키 이벤트).
# 트리거 규칙은 보통 완성형 한글("안녕하세요")로 등록되므로, 들어온
# 자모를 실시간으로 조합해 "화면에 보이는 형태"를 재구성해야 매칭이 된다.
#
# 호환용 자모(U+3131~)와 현대 한글 자모(U+1100~)를 모두 같은
# 내부 표현(호환용 자모)으로 정규화한 뒤 조합한다.

_CHO  = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")            # 19
_JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")          # 21
_JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")  # 28 (0=받침 없음)

_CHO_IDX  = {c: i for i, c in enumerate(_CHO)}
_JUNG_IDX = {c: i for i, c in enumerate(_JUNG)}
_JONG_IDX = {c: i + 1 for i, c in enumerate(_JONG[1:])}

# 모음 합성: (기존 중성, 새 입력) -> 합성된 중성
_JUNG_COMBINE = {
    ("ㅗ", "ㅏ"): "ㅘ", ("ㅗ", "ㅐ"): "ㅙ", ("ㅗ", "ㅣ"): "ㅚ",
    ("ㅜ", "ㅓ"): "ㅝ", ("ㅜ", "ㅔ"): "ㅞ", ("ㅜ", "ㅣ"): "ㅟ",
    ("ㅡ", "ㅣ"): "ㅢ",
}
# 받침 합성: (기존 종성, 새 입력) -> 합성된 종성
_JONG_COMBINE = {
    ("ㄱ", "ㅅ"): "ㄳ", ("ㄴ", "ㅈ"): "ㄵ", ("ㄴ", "ㅎ"): "ㄶ",
    ("ㄹ", "ㄱ"): "ㄺ", ("ㄹ", "ㅁ"): "ㄻ", ("ㄹ", "ㅂ"): "ㄼ",
    ("ㄹ", "ㅅ"): "ㄽ", ("ㄹ", "ㅌ"): "ㄾ", ("ㄹ", "ㅍ"): "ㄿ",
    ("ㄹ", "ㅎ"): "ㅀ", ("ㅂ", "ㅅ"): "ㅄ",
}
# 겹받침 분리: 합성된 받침 -> (남는 받침, 다음 음절의 초성이 될 자음)
_JONG_SPLIT = {v: k for k, v in _JONG_COMBINE.items()}

# 현대 한글 자모(U+1100~) -> 호환용 자모로 정규화하는 표
_MODERN_TO_COMPAT = {}
for _i, _c in enumerate(_CHO):
    _MODERN_TO_COMPAT[chr(0x1100 + _i)] = _c
for _i, _c in enumerate(_JUNG):
    _MODERN_TO_COMPAT[chr(0x1161 + _i)] = _c
for _i, _c in enumerate(_JONG[1:]):
    _MODERN_TO_COMPAT[chr(0x11A8 + _i)] = _c


def _make_syllable(cho: str, jung: str, jong: str = "") -> str:
    ci = _CHO_IDX[cho]
    vi = _JUNG_IDX[jung]
    ji = _JONG_IDX.get(jong, 0)
    return chr(0xAC00 + (ci * 21 + vi) * 28 + ji)


def compose_hangul(raw: str) -> str:
    """두벌식 자모 입력 시퀀스를 화면에 표시되는 형태(조합형)로 변환.
    한글 자모가 아닌 문자(영문/숫자/완성된 한글 음절/기호 등)는
    그대로 통과시킨다."""
    result = []
    cho = jung = jong = None

    def flush():
        nonlocal cho, jung, jong
        if cho is not None and jung is not None:
            result.append(_make_syllable(cho, jung, jong or ""))
        elif cho is not None:
            result.append(cho)
        elif jung is not None:
            result.append(jung)
        cho = jung = jong = None

    for raw_c in raw:
        c = _MODERN_TO_COMPAT.get(raw_c, raw_c)
        is_cho = c in _CHO_IDX
        is_jung = c in _JUNG_IDX

        if not is_cho and not is_jung:
            flush()
            result.append(raw_c)  # 원래 문자 그대로 출력 (정규화 전 형태)
            continue

        if cho is None and jung is None:
            if is_cho:
                cho = c
            else:
                result.append(c)  # 단독 모음, 즉시 확정
            continue

        if jung is None:  # 초성만 있음
            if is_jung:
                jung = c
            else:
                flush()
                cho = c
            continue

        if jong is None:  # 초성+중성 (받침 없음)
            if is_jung:
                combo = _JUNG_COMBINE.get((jung, c))
                if combo:
                    jung = combo
                else:
                    flush()
                    result.append(c)  # 새 음절은 단독 모음으로 즉시 확정
            else:
                jong = c
            continue

        # 초성+중성+받침
        if is_jung:
            if jong in _JONG_SPLIT:
                remain, moved = _JONG_SPLIT[jong]
                jong = remain
                flush()
                cho = moved
                jung = c
            else:
                moved = jong
                jong = None
                flush()
                cho = moved
                jung = c
        else:
            combo = _JONG_COMBINE.get((jong, c))
            if combo:
                jong = combo
            else:
                flush()
                cho = c

    flush()
    return "".join(result)

# ── 키보드 리스너 (백그라운드 스레드) ───────────────────────────
class KeyboardListener(QObject):
    status_changed = pyqtSignal(str)

    # ── 입력 주입 타이밍 ─────────────────────────────────────────
    # 트리거 삭제는 백스페이스(단일 키 반복, 순서 문제 없음)로,
    # 새 텍스트 입력은 유니코드 직접 주입(send_unicode_string)으로 처리한다.
    #   - 단일 SendInput 호출로 모든 글자를 보내 순서가 절대 뒤섞이지 않음
    #     (예전 "2026-063-1" 류 순서 꼬임 없음)
    #   - IME를 거치지 않아 한글 조합형/분리형 문제 없음
    #   - 클립보드/붙여넣기 단축키에 의존하지 않아 터미널에서도 동일 동작
    _BACKSPACE_DELAY   = 0.008   # 백스페이스 1개당 지연
    _PRE_TYPE_DELAY    = 0.02    # 백스페이스 완료 후 텍스트 주입 시작 전 지연
    _TYPE_CHAR_DELAY   = 0.01    # 주입 글자 1개당 지연(send_text char_delay 와 일치)
    _POST_TYPE_DELAY   = 0.03    # 텍스트 주입 후 안정화 대기

    # 위 지연들을 합산한 "억제 시간" 보정 마진
    _SUPPRESS_MARGIN = 0.05
    _SUPPRESS_MIN = 0.05
    _SUPPRESS_MAX = 1.5

    def __init__(self):
        super().__init__()
        self.rules = []
        self.active = True
        self.buffer = ""     # 원본(분리형) 입력 시퀀스
        self.composed = ""   # 한글 자모를 조합한, 화면에 보이는 형태
        self.controller = Controller()
        self._listener = None
        self._lock = threading.Lock()
        # _do_replace가 controller로 보낸 합성 입력이 다시 on_press로
        # 들어와 버퍼를 오염시키는 것을 막기 위한 "억제 만료 시각"
        # (카운팅 방식이 아니라 시간 기반이라 추정이 틀려도 자동 복구됨)
        self._suppress_until = 0.0
        # _do_replace 실행 중 재귀적으로 다시 호출되는 것을 막는 플래그
        self._replacing = False

        # ── 빠른 필터링용 인덱스 (set_rules에서 갱신) ──────────────
        # 매 키 입력마다 모든 규칙을 endswith()로 검사하지 않고,
        # "트리거의 마지막 글자"가 일치하는 경우에만 정밀 검사를 수행한다.
        # 한글 트리거는 조합형/분리형 양쪽의 마지막 글자를 모두 포함한다.
        # → 전역 후크 콜백이 매 키마다 최소한의 작업만 하도록 보장.
        self._special_last_chars = set()
        self._word_last_chars = set()
        self._has_regex = False

    def set_rules(self, rules):
        with self._lock:
            self.rules = [r for r in rules if r.get("enabled", True)]
            self._special_last_chars = self._collect_last_chars("special")
            self._word_last_chars = self._collect_last_chars("word")
            self._has_regex = any(r["type"] == "regex" for r in self.rules)

    def _collect_last_chars(self, rule_type):
        """트리거의 마지막 글자를 원본(분리형)·조합형 양쪽 다 수집한다.
        예: 트리거가 한글 자모 시퀀스("ㅎㄴㅇ")든 완성형("한녕")이든
        둘 다 빠른 필터에 걸리도록 한다."""
        chars = set()
        for r in self.rules:
            if r["type"] != rule_type or not r["trigger"]:
                continue
            trig = r["trigger"]
            chars.add(trig[-1])
            comp = compose_hangul(trig)
            if comp:
                chars.add(comp[-1])
        return chars

    def set_active(self, val: bool):
        self.active = val
        if not val:
            self.buffer = ""
            self.composed = ""
            self._suppress_until = 0.0

    def _on_press(self, key):
        if not self.active:
            return

        # 1) 우리가 controller로 직접 보낸(자가 입력) 이벤트는 무시
        #    -> 시간 기반이므로, 추정이 틀려도 시간이 지나면 자동 해제됨
        if time.monotonic() < self._suppress_until:
            return

        try:
            ch = key.char
        except AttributeError:
            ch = None

        if ch is None:
            # 특수키 (Ctrl, Alt, F1~F12, 한자/한영키 등) → char가 None
            if key in (Key.space, Key.enter):
                self._check_and_replace(append=" " if key == Key.space else "\n")
            elif key == Key.backspace:
                self.buffer = self.buffer[:-1]
                self.composed = compose_hangul(self.buffer)
            else:
                self.buffer = ""
                self.composed = ""
            return

        self.buffer += ch
        if len(self.buffer) > 200:
            self.buffer = self.buffer[-200:]
        # 한글 자모(분리형)를 조합해 화면에 보이는 형태(조합형)로 재구성.
        # 매번 전체를 재조합하므로, 받침이 다음 음절 초성으로 옮겨가는
        # 재구성("간"+ㅏ → "가"+"나") 같은 경우도 항상 정확하다.
        self.composed = compose_hangul(self.buffer)
        self._check_immediate()

    def _check_immediate(self):
        if not self.buffer:
            return
        with self._lock:
            last_chars = self._special_last_chars
            rules = self.rules[:]

        last_raw = self.buffer[-1]
        last_comp = self.composed[-1] if self.composed else ""
        # 1) 빠른 필터: 등록된 special 트리거 중 마지막 글자가
        #    (분리형/조합형 어느 쪽으로든) 일치하지 않으면 즉시 종료
        if last_raw not in last_chars and last_comp not in last_chars:
            return

        for rule in rules:
            if rule["type"] != "special":
                continue
            trig = rule["trigger"]
            # 조합형(완성된 한글 등) 우선 검사
            if self.composed.endswith(trig):
                self._do_replace(trig, rule["output"], via="composed")
                return
            # 분리형(자모 시퀀스 그대로) 검사
            if self.buffer.endswith(trig):
                self._do_replace(trig, rule["output"], via="raw")
                return

    def _check_and_replace(self, append=""):
        with self._lock:
            rules = self.rules[:]
            word_last_chars = self._word_last_chars
            has_regex = self._has_regex

        buf = self.buffer
        comp = self.composed
        last_raw = buf[-1] if buf else ""
        last_comp = comp[-1] if comp else ""

        # 1) word 트리거: 마지막 글자가 등록된 트리거의 마지막 글자와
        #    (분리형/조합형 어느 쪽이든) 일치할 때만 정밀 검사
        if last_raw in word_last_chars or last_comp in word_last_chars:
            for rule in rules:
                if rule["type"] != "word":
                    continue
                trig = rule["trigger"]
                if comp.endswith(trig):
                    self._do_replace(trig, rule["output"], extra=append, via="composed")
                    return
                if buf.endswith(trig):
                    self._do_replace(trig, rule["output"], extra=append, via="raw")
                    return

        # 2) regex 트리거가 하나라도 등록된 경우에만 검사 (조합형 기준)
        if has_regex:
            for rule in rules:
                if rule["type"] == "regex":
                    m = re.search(rule["trigger"] + r"$", comp)
                    if m:
                        self._do_replace(m.group(0), rule["output"], extra=append, via="composed")
                        return

        self.buffer += append
        self.composed = compose_hangul(self.buffer)

    def _do_replace(self, trigger: str, output: str, extra: str = "", via: str = "composed"):
        # 재귀/중첩 호출 방어: 이전 치환의 입력 주입이 아직 진행 중이면 무시
        if self._replacing:
            return
        self._replacing = True

        resolved = resolve_output(output)
        to_type = resolved + extra

        # 화면에서 지워야 할 "보이는 글자 수"를 계산한다.
        # - via="raw": 트리거 자체가 그대로 입력/표시된 경우 (영문/숫자 등)
        #              → 글자 수 = len(trigger)
        # - via="composed": 트리거가 한글 자모 조합 결과로 매칭된 경우
        #              → 화면에는 조합된 형태(compose_hangul(trigger))로
        #                보이므로, 그 길이만큼만 백스페이스하면 됨
        #                (한글 1글자 = 백스페이스 1번, 자모 개수와 무관)
        if via == "raw":
            trigger_backspaces = len(trigger)
        else:
            trigger_backspaces = len(compose_hangul(trigger)) or len(trigger)

        # extra(스페이스/엔터)는 word/regex 트리거를 완성시킨 "그 키 입력"인데,
        # suppress=False라 이미 화면에 정상적으로 찍혀 있는 상태다.
        # 즉 백스페이스 시점의 화면 = trigger 부분 + extra 1글자.
        # 이걸 빼놓으면 trigger의 첫 글자가 안 지워지고 남는다
        # (예: "abc"+스페이스 → 3번만 지우면 "a123 "이 됨. 4번 지워야 "123 ").
        backspace_count = trigger_backspaces + len(extra)

        # 실제 입력 주입(백스페이스+붙여넣기)에 걸릴 예상 시간을 계산해
        # 그동안의 키 이벤트는 무시(억제)한다.
        # 클립보드 붙여넣기는 텍스트 길이와 거의 무관하게 일정 시간이
        # 걸리므로, to_type 길이에 비례하지 않는다.
        # → 추정이 다소 틀려도 일정 시간 뒤 자동 해제되어
        #   "한 번 꼬이면 영구 복구 안 됨" 문제가 발생하지 않음.
        est = (backspace_count * self._BACKSPACE_DELAY
               + self._PRE_TYPE_DELAY
               + len(to_type) * self._TYPE_CHAR_DELAY
               + self._POST_TYPE_DELAY
               + self._SUPPRESS_MARGIN)
        duration = max(self._SUPPRESS_MIN, min(self._SUPPRESS_MAX, est))
        self._suppress_until = time.monotonic() + duration

        # 버퍼는 즉시(동기적으로) 갱신 → 이후 들어오는 키 입력은
        # 올바른 버퍼 상태를 기준으로 처리됨.
        if via == "raw" and trigger and self.buffer.endswith(trigger):
            # 분리형 매칭: 트리거가 입력 그대로이므로 정확히 잘라낼 수 있음
            self.buffer = self.buffer[:-len(trigger)] + to_type
        else:
            # 조합형 매칭: 트리거 이전의 원본 자모 시퀀스를 정확히
            # 역산하기 어려우므로(받침 재구성 등), 버퍼를 결과 텍스트
            # 기준으로 재설정한다. (compose_hangul(to_type) == to_type
            # 이므로 이후 입력에 영향 없음)
            self.buffer = to_type
        self.composed = compose_hangul(self.buffer)

        # 실제 키 입력 주입은 백그라운드 스레드에서 처리한다.
        # 1) 후킹 콜백을 즉시 반환시켜 다른 키 입력을 막지(블로킹) 않음
        # 2) 백스페이스 → (지연) → 붙여넣기 순서로 보내 race condition 방지
        threading.Thread(
            target=self._inject_replacement,
            args=(trigger, to_type, resolved, backspace_count),
            daemon=True,
        ).start()

    def _inject_replacement(self, trigger: str, to_type: str, resolved: str, backspace_count: int):
        try:
            # 1) 화면에 보이는 글자 수(backspace_count)만큼 백스페이스를
            #    "한 글자씩" 보내고, 대상 앱이 처리할 시간을 준다.
            #    (단일 키의 반복이라 순서가 뒤섞일 일이 없음.
            #     한글 음절도 백스페이스 1번에 1글자씩 지워짐)
            for _ in range(backspace_count):
                self.controller.press(Key.backspace)
                self.controller.release(Key.backspace)
                time.sleep(self._BACKSPACE_DELAY)

            # 2) 백스페이스가 모두 처리되도록 잠시 대기
            time.sleep(self._PRE_TYPE_DELAY)

            # 3) 새 텍스트는 스캔코드 키 이벤트로 직접 주입한다.
            #    실제 키보드처럼 보내므로 GUI 앱뿐 아니라 PowerShell
            #    PSReadLine·cmd·readline 같은 콘솔 줄 편집기도 정상 인식한다
            #    (유니코드 주입은 콘솔 줄 편집기가 흘려버려 터미널에서 실패).
            #    글자 단위로 순서대로 보내고 짧게 지연해 순서 꼬임을 막는다.
            #    키보드로 칠 수 없는 글자(한글 등)는 send_text 내부에서
            #    유니코드로 폴백한다. 클립보드는 건드리지 않는다.
            if not send_text(to_type):
                # 폴백: 비-Windows이거나 주입 실패 시 pynput 타이핑
                self.controller.type(to_type)
            time.sleep(self._POST_TYPE_DELAY)

            self.status_changed.emit(f'"{trigger}" → "{resolved}"')
        finally:
            self._replacing = False

    def start(self):
        # suppress=False (기본값) : 모든 키 이벤트를 가로채거나 차단하지 않고
        # 그대로 OS/대상 앱에 전달한다. 이 리스너는 "관찰"만 하며,
        # 등록된 트리거가 완성됐을 때만 백스페이스+재입력으로 치환한다.
        self._listener = keyboard.Listener(on_press=self._on_press, suppress=False)
        self._listener.start()

    def stop(self):
        if self._listener:
            self._listener.stop()



# ── 규칙 추가/편집 다이얼로그 ────────────────────────────────────
class RuleDialog(QDialog):
    def __init__(self, parent=None, rule=None):
        super().__init__(parent)
        self.setWindowTitle("규칙 편집" if rule else "규칙 추가")
        self.setFixedSize(420, 320)
        self.setStyleSheet(parent.styleSheet() if parent else "")

        layout = QFormLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        self.type_combo = QComboBox()
        self.type_combo.addItems(["word (단어)", "special (;단축어)", "regex (정규식)"])
        self.trigger_edit = QLineEdit()
        self.trigger_edit.setPlaceholderText("예: abc  또는  ;date  또는  \\d{4}")
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("예: 123  또는  {date}  또는  [DATE]")

        layout.addRow("타입",   self.type_combo)
        layout.addRow("트리거", self.trigger_edit)
        layout.addRow("출력",   self.output_edit)

        # ── 실시간 미리보기 ──────────────────────────────────────
        # 출력 필드에 {date:%Y%m%d} 같은 형식을 입력하면, 실제
        # 변환됐을 때 어떤 텍스트가 들어가는지 즉시 보여준다.
        # (strftime 코드 대소문자 실수를 저장 전에 바로 확인 가능)
        self.preview_label = QLabel()
        self.preview_label.setStyleSheet(
            "color: #4ADE80; font-size: 12px; font-weight: 600; "
            "background: #141620; border: 1px solid #252840; "
            "border-radius: 6px; padding: 6px 10px;"
        )
        self.preview_label.setWordWrap(True)
        layout.addRow("미리보기", self.preview_label)
        self.output_edit.textChanged.connect(self._update_preview)
        self._update_preview()

        hint = QLabel(
            "특수 변수: {date} {time} {datetime}\n"
            "형식 지정: {date:%Y%m%d} → 20260613   {time:%H:%M} → 20:03\n"
            "           {date:%m-%d} → 06-13"
        )
        hint.setStyleSheet("color: #888; font-size: 11px;")
        layout.addRow("", hint)

        btn_row = QHBoxLayout()
        ok_btn     = QPushButton("저장")
        ok_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("취소")
        cancel_btn.setObjectName("secondary")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(ok_btn)
        layout.addRow("", btn_row)

        if rule:
            type_map = {"word": 0, "special": 1, "regex": 2}
            self.type_combo.setCurrentIndex(type_map.get(rule["type"], 0))
            self.trigger_edit.setText(rule["trigger"])
            self.output_edit.setText(rule["output"])
            self._update_preview()

    def _update_preview(self):
        text = self.output_edit.text()
        if not text:
            self.preview_label.setText("(출력 내용을 입력하세요)")
            self.preview_label.setStyleSheet(
                "color: #666; font-size: 12px; "
                "background: #141620; border: 1px solid #252840; "
                "border-radius: 6px; padding: 6px 10px;"
            )
            return
        try:
            preview = resolve_output(text)
            self.preview_label.setText(f"→ {preview}")
            self.preview_label.setStyleSheet(
                "color: #4ADE80; font-size: 12px; font-weight: 600; "
                "background: #141620; border: 1px solid #252840; "
                "border-radius: 6px; padding: 6px 10px;"
            )
        except Exception as e:
            self.preview_label.setText(f"형식 오류: {e}")
            self.preview_label.setStyleSheet(
                "color: #F87171; font-size: 12px; font-weight: 600; "
                "background: #141620; border: 1px solid #5A2A2A; "
                "border-radius: 6px; padding: 6px 10px;"
            )

    def get_rule(self):
        type_map = {0: "word", 1: "special", 2: "regex"}
        return {
            "type":    type_map[self.type_combo.currentIndex()],
            "trigger": self.trigger_edit.text().strip(),
            "output":  self.output_edit.text().strip(),
            "enabled": True,
        }


# ── 드래그로 행 순서 변경 가능한 테이블 ───────────────────────────
class RulesTable(QTableWidget):
    """체크박스 등 셀 위젯이 있는 QTableWidget은 내부 모델의
    rowsMoved 신호가 신뢰성 있게 발생하지 않을 수 있다.
    dropEvent를 직접 오버라이드해 "드롭이 끝난 직후" 콜백을
    호출하는 방식으로 순서 변경을 확실하게 감지한다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.drop_callback = None

    def dropEvent(self, event):
        super().dropEvent(event)
        if self.drop_callback:
            self.drop_callback()


# ── 메인 윈도우 ──────────────────────────────────────────────────
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("KeyFlux")
        self.setMinimumSize(700, 540)
        self.rules = load_rules()
        self._apply_style()
        self._init_listener()
        self._build_ui()
        self._build_tray()
        self._connect_listener_signals()

    # ── 스타일 ───────────────────────────────────────────────────
    def _apply_style(self):
        self.setStyleSheet("""
            QMainWindow, QDialog { background: #0F1117; }
            QWidget { background: #0F1117; color: #E8E8F0;
                      font-family: 'Segoe UI', 'Apple SD Gothic Neo', sans-serif;
                      font-size: 13px; }

            QLabel#title    { font-size: 22px; font-weight: 700; color: #FFFFFF; letter-spacing: 1px; }
            QLabel#subtitle { font-size: 12px; color: #666; }
            QLabel#status_label { font-size: 12px; color: #888; }

            QPushButton {
                background: #7C5CBF; color: #fff;
                border: none; border-radius: 6px;
                padding: 7px 18px; font-weight: 600;
            }
            QPushButton:hover   { background: #9370DB; }
            QPushButton:pressed { background: #6A4FA8; }

            QPushButton[objectName="secondary"] {
                background: #1E2030; color: #AAA; border: 1px solid #333; }
            QPushButton[objectName="secondary"]:hover { background: #252840; }

            QPushButton[objectName="danger"] {
                background: #3D1F2D; color: #E05080; border: 1px solid #5A2040; }
            QPushButton[objectName="danger"]:hover { background: #4D2535; }

            QPushButton[objectName="toggle_on"] {
                background: #1A3A2A; color: #4ADE80; border: 1px solid #2A5A3A;
                font-weight: 700; min-width: 110px; }
            QPushButton[objectName="toggle_off"] {
                background: #3A1A1A; color: #F87171; border: 1px solid #5A2A2A;
                font-weight: 700; min-width: 110px; }

            QTableWidget {
                background: #141620; border: 1px solid #252840;
                border-radius: 8px; gridline-color: #1E2030;
                selection-background-color: #2A2050; }
            QTableWidget::item { padding: 6px 10px; border-bottom: 1px solid #1A1C2E; }
            QTableWidget::item:selected { background: #2A2050; color: #fff; }
            QHeaderView::section {
                background: #0F1117; color: #666; font-weight: 600;
                font-size: 11px; letter-spacing: 1px;
                border: none; border-bottom: 1px solid #252840; padding: 8px 10px; }

            QLineEdit {
                background: #141620; border: 1px solid #252840;
                border-radius: 6px; padding: 7px 10px; color: #E8E8F0; }
            QLineEdit:focus { border-color: #7C5CBF; }

            QComboBox {
                background: #141620; border: 1px solid #252840;
                border-radius: 6px; padding: 6px 10px; color: #E8E8F0; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background: #141620; border: 1px solid #252840; }

            QFrame#divider { background: #1E2030; max-height: 1px; }

            QCheckBox::indicator {
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid #444; background: #141620; }
            QCheckBox::indicator:checked { background: #7C5CBF; border-color: #7C5CBF; }
        """)

    # ── UI 구성 ──────────────────────────────────────────────────
    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        # 헤더
        header = QHBoxLayout()
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        t = QLabel("KeyFlux")
        t.setObjectName("title")
        sub = QLabel("키 입력 자동 변환 · 백그라운드 실행")
        sub.setObjectName("subtitle")
        title_col.addWidget(t)
        title_col.addWidget(sub)

        self.toggle_btn = QPushButton("● 활성화됨")
        self.toggle_btn.setObjectName("toggle_on")
        self.toggle_btn.clicked.connect(self._toggle_active)

        header.addLayout(title_col)
        header.addStretch()
        header.addWidget(self.toggle_btn)
        root.addLayout(header)
        root.addSpacing(20)

        divider = QFrame()
        divider.setObjectName("divider")
        divider.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(divider)
        root.addSpacing(16)

        # 도구모음
        toolbar = QHBoxLayout()
        toolbar.setSpacing(6)

        add_btn = QPushButton("+ 규칙 추가")
        add_btn.clicked.connect(self._add_rule)

        edit_btn = QPushButton("편집")
        edit_btn.setObjectName("secondary")
        edit_btn.clicked.connect(self._edit_rule)

        del_btn = QPushButton("삭제")
        del_btn.setObjectName("danger")
        del_btn.clicked.connect(self._delete_rule)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #252840;")
        sep.setFixedWidth(1)

        export_btn = QPushButton("↑ 내보내기")
        export_btn.setObjectName("secondary")
        export_btn.setToolTip("현재 규칙을 JSON 파일로 저장합니다")
        export_btn.clicked.connect(self._export_rules)

        import_btn = QPushButton("↓ 불러오기")
        import_btn.setObjectName("secondary")
        import_btn.setToolTip("JSON 파일에서 규칙을 불러옵니다")
        import_btn.clicked.connect(self._import_rules)

        toolbar.addWidget(add_btn)
        toolbar.addWidget(edit_btn)
        toolbar.addWidget(del_btn)
        toolbar.addSpacing(8)
        toolbar.addWidget(sep)
        toolbar.addSpacing(8)
        toolbar.addWidget(export_btn)
        toolbar.addWidget(import_btn)
        toolbar.addStretch()
        root.addLayout(toolbar)
        root.addSpacing(10)

        # 테이블
        self.table = RulesTable()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["활성", "타입", "트리거", "출력"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 48)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(1, 90)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)

        # 드래그로 행 순서 변경 가능하게 설정
        self.table.setDragDropMode(QTableWidget.DragDropMode.InternalMove)
        self.table.setDragEnabled(True)
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True)
        self.table.setDragDropOverwriteMode(False)
        # 드롭이 끝난 직후 self.rules 순서를 새 화면 순서에 맞춰 갱신
        self.table.drop_callback = self._on_table_reordered

        # 더블클릭 시 편집 창 열기
        self.table.cellDoubleClicked.connect(self._on_cell_double_clicked)

        root.addWidget(self.table)
        root.addSpacing(12)

        # 상태바
        status_row = QHBoxLayout()
        self.status_label = QLabel("대기 중...")
        self.status_label.setObjectName("status_label")

        self.config_path_label = QLabel(f"설정 파일: {DATA_FILE}")
        self.config_path_label.setObjectName("status_label")
        self.config_path_label.setToolTip(str(DATA_FILE))

        status_row.addWidget(self.status_label)
        status_row.addStretch()
        status_row.addWidget(self.config_path_label)
        root.addLayout(status_row)

        self._refresh_table()

    # ── 테이블 갱신 ──────────────────────────────────────────────
    def _refresh_table(self):
        self.table.setRowCount(0)
        type_colors = {"word": "#7C5CBF", "special": "#2A8FBF", "regex": "#BF7C2A"}
        for i, rule in enumerate(self.rules):
            self.table.insertRow(i)

            chk = QCheckBox()
            chk.setChecked(rule.get("enabled", True))
            chk.stateChanged.connect(lambda state, idx=i: self._toggle_rule(idx, state))
            cell = QWidget()
            lay = QHBoxLayout(cell)
            lay.setContentsMargins(0, 0, 0, 0)
            lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lay.addWidget(chk)
            self.table.setCellWidget(i, 0, cell)

            type_item = QTableWidgetItem(rule["type"])
            type_item.setForeground(QColor(type_colors.get(rule["type"], "#888")))
            type_font = QFont("Segoe UI")
            type_font.setPointSize(11)
            type_font.setBold(True)
            type_item.setFont(type_font)
            # 드래그로 행이 이동된 뒤 새 순서를 알아내기 위해, 현재
            # self.rules에서의 원래 인덱스(정수)를 아이템에 저장해둔다.
            # (정수는 Qt의 드래그&드롭 MIME 직렬화에서 안전하게 보존됨.
            #  규칙 dict 자체를 저장하면 직렬화 과정에서 깨질 수 있음)
            type_item.setData(Qt.ItemDataRole.UserRole, i)
            self.table.setItem(i, 1, type_item)
            self.table.setItem(i, 2, QTableWidgetItem(rule["trigger"]))
            self.table.setItem(i, 3, QTableWidgetItem(rule["output"]))
            self.table.setRowHeight(i, 40)

        self.listener.set_rules(self.rules)

    # ── 드래그로 행 순서 변경 ──────────────────────────────────────
    def _on_table_reordered(self):
        """행 드래그&드롭이 끝난 직후 호출됨.
        각 행에 저장해둔 "원래 인덱스"를 화면에 보이는 새 순서대로
        읽어 self.rules를 재배열하고 즉시 설정 파일에 저장한다.
        체크박스 등 셀 위젯은 Qt가 자동으로 옮겨주지 않으므로
        새 순서를 기준으로 다시 그린다."""
        old_rules = self.rules
        new_rules = []
        seen = set()

        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if item is None:
                continue
            idx = item.data(Qt.ItemDataRole.UserRole)
            if isinstance(idx, int) and 0 <= idx < len(old_rules) and idx not in seen:
                new_rules.append(old_rules[idx])
                seen.add(idx)

        # 누락된 항목이 있으면(예외적 상황) 끝에 보존
        for idx in range(len(old_rules)):
            if idx not in seen:
                new_rules.append(old_rules[idx])

        if new_rules != old_rules:
            self.rules = new_rules
            save_rules(self.rules)  # 새 순서를 설정 파일에 즉시 반영

        # 셀 위젯(체크박스)을 새 순서에 맞춰 다시 그림
        QTimer.singleShot(0, self._refresh_table)

    # ── 더블클릭으로 편집 창 열기 ────────────────────────────────
    def _on_cell_double_clicked(self, row, column):
        self.table.setCurrentCell(row, column)
        self._edit_rule()

    # ── 규칙 CRUD ────────────────────────────────────────────────
    def _add_rule(self):
        dlg = RuleDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            rule = dlg.get_rule()
            if rule["trigger"] and rule["output"]:
                self.rules.append(rule)
                save_rules(self.rules)
                self._refresh_table()

    def _edit_rule(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "알림", "편집할 규칙을 선택하세요.")
            return
        dlg = RuleDialog(self, self.rules[row])
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_rule = dlg.get_rule()
            new_rule["enabled"] = self.rules[row].get("enabled", True)
            self.rules[row] = new_rule
            save_rules(self.rules)
            self._refresh_table()

    def _delete_rule(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "알림", "삭제할 규칙을 선택하세요.")
            return
        trigger = self.rules[row]["trigger"]
        reply = QMessageBox.question(self, "삭제 확인", f'"{trigger}" 규칙을 삭제할까요?')
        if reply == QMessageBox.StandardButton.Yes:
            self.rules.pop(row)
            save_rules(self.rules)
            self._refresh_table()

    def _toggle_rule(self, idx, state):
        if idx < len(self.rules):
            self.rules[idx]["enabled"] = bool(state)
            save_rules(self.rules)
            self.listener.set_rules(self.rules)

    # ── 설정 내보내기 / 불러오기 ─────────────────────────────────
    def _export_rules(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "규칙 내보내기", "textshift_rules.json",
            "JSON 파일 (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, ensure_ascii=False, indent=2)
            QMessageBox.information(self, "완료", f"규칙을 저장했습니다.\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "오류", f"저장 실패: {e}")

    def _import_rules(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "규칙 불러오기", "",
            "JSON 파일 (*.json)"
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # 기본 유효성 검사
            if not isinstance(loaded, list):
                raise ValueError("규칙 목록이 배열 형식이 아닙니다.")
            for r in loaded:
                if not all(k in r for k in ("type", "trigger", "output")):
                    raise ValueError(f"잘못된 규칙 항목: {r}")

            reply = QMessageBox.question(
                self, "불러오기 방식",
                "기존 규칙을 대체할까요?\n\n[Yes] 대체   [No] 기존에 추가",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No  |
                QMessageBox.StandardButton.Cancel
            )
            if reply == QMessageBox.StandardButton.Cancel:
                return
            if reply == QMessageBox.StandardButton.Yes:
                self.rules = loaded
            else:
                # 중복 트리거 스킵
                existing = {r["trigger"] for r in self.rules}
                added = 0
                for r in loaded:
                    if r["trigger"] not in existing:
                        self.rules.append(r)
                        existing.add(r["trigger"])
                        added += 1
                QMessageBox.information(self, "완료", f"{added}개 규칙을 추가했습니다.")

            save_rules(self.rules)
            self._refresh_table()
        except Exception as e:
            QMessageBox.critical(self, "오류", f"불러오기 실패: {e}")

    # ── 전체 활성/비활성 ─────────────────────────────────────────
    def _toggle_active(self):
        is_active = self.listener.active
        self.listener.set_active(not is_active)
        if not is_active:
            self.toggle_btn.setText("● 활성화됨")
            self.toggle_btn.setObjectName("toggle_on")
            self.status_label.setText("대기 중...")
        else:
            self.toggle_btn.setText("○ 비활성화됨")
            self.toggle_btn.setObjectName("toggle_off")
            self.status_label.setText("변환 중지됨")
        self.toggle_btn.style().unpolish(self.toggle_btn)
        self.toggle_btn.style().polish(self.toggle_btn)

    # ── 트레이 아이콘 ────────────────────────────────────────────
    def _build_tray(self):
        pix = QPixmap(32, 32)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QColor("#7C5CBF"))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(0, 0, 32, 32, 6, 6)
        painter.setPen(QColor("#FFFFFF"))
        icon_font = QFont("Arial")
        icon_font.setPointSize(16)
        icon_font.setBold(True)
        painter.setFont(icon_font)
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "K")
        painter.end()

        self.tray = QSystemTrayIcon(QIcon(pix), self)
        menu = QMenu()
        menu.addAction("열기").triggered.connect(self.show)
        menu.addAction("활성화 토글").triggered.connect(self._toggle_active)
        menu.addSeparator()
        menu.addAction("종료").triggered.connect(QApplication.quit)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(
            lambda r: self.show() if r == QSystemTrayIcon.ActivationReason.DoubleClick else None
        )
        self.tray.show()
        self.tray.setToolTip("KeyFlux - 실행 중")

    # ── 리스너 생성/시작 ─────────────────────────────────────────
    def _init_listener(self):
        """UI 빌드 전에 listener 객체를 먼저 생성 (rules 참조용)"""
        self.listener = KeyboardListener()
        self.listener.set_rules(self.rules)

    def _connect_listener_signals(self):
        """UI(트레이/상태바)가 준비된 후 신호 연결 + 후킹 시작"""
        self.listener.status_changed.connect(self._on_status)
        self.listener.start()

    def _on_status(self, msg):
        self.status_label.setText(f"변환됨: {msg}")
        self.tray.showMessage("KeyFlux", msg, QSystemTrayIcon.MessageIcon.NoIcon, 1500)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage("KeyFlux", "트레이에서 계속 실행 중입니다.",
                              QSystemTrayIcon.MessageIcon.Information, 2000)


# ── 진입점 ───────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)

    # ── 중복 실행 방지 (Single Instance Check) ────────────────────
    # KeyFlux는 키보드 후킹을 수행하므로, 여러 프로세스가 동시에 실행되면
    # 한 번의 키 입력에 대해 중복 치환이 발생할 수 있다 (결과가 두 번 나옴).
    # 이를 방지하기 위해 공유 메모리를 사용하여 단일 인스턴스 실행을 보장한다.
    shared_mem_key = "KeyFlux_SingleInstance_SharedMem"
    shared_mem = QSharedMemory(shared_mem_key)
    
    # create(1) 시도: 이미 존재하면 False 반환
    if not shared_mem.create(1):
        # 이미 메모리가 점유되어 있다면 실행 중인 것.
        # 비정상 종료 시 메모리가 남을 수 있으므로 attach로 실제 존재 여부 확인.
        if shared_mem.attach():
            QMessageBox.warning(None, "KeyFlux", "프로그램이 이미 실행 중입니다.\n트레이 아이콘을 확인하세요.")
            sys.exit(0)

    app.setQuitOnLastWindowClosed(False)
    # 일부 Windows 환경에서 기본 폰트의 pointSize가 -1로 잡혀
    # "QFont::setPointSize: Point size <= 0 (-1)" 경고가 뜨는 것을 방지
    default_font = QFont("Segoe UI")
    default_font.setPointSize(10)
    app.setFont(default_font)

    win = MainWindow()
    win.show()

    # Ctrl+C(SIGINT)로 종료 가능하게 설정.
    # Qt의 이벤트 루프(app.exec())는 C++ 레벨에서 도는 동안 Python이
    # 바이트코드를 실행할 기회가 없어서, 기본적으로는 Ctrl+C가 무시된다.
    # SIGINT 핸들러를 기본값으로 되돌리고, 주기적으로 빈 타이머를
    # 실행시켜 Python 인터프리터에게 제어권을 짧게 돌려주면
    # 그 사이에 시그널이 처리되어 Ctrl+C가 정상 동작한다.
    signal.signal(signal.SIGINT, signal.SIG_DFL)
    _sigint_timer = QTimer()
    _sigint_timer.timeout.connect(lambda: None)
    _sigint_timer.start(200)

    try:
        sys.exit(app.exec())
    except KeyboardInterrupt:
        print("\nKeyFlux 종료됨 (Ctrl+C)")
        sys.exit(0)

if __name__ == "__main__":
    main()
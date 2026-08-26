"""KeyFlux 핵심 로직 테스트 (GUI/실제 키 주입 없이 순수 로직만 검증).

실행:
    python -m unittest discover -s tests -v
    또는
    python -m pytest tests -q   (pytest 가 있으면)

KeyboardListener 의 실제 치환(_do_replace / _do_replace_norm)은 OS 에 키를
주입하므로, 테스트에서는 이를 가짜 함수로 바꿔 "어떤 트리거가 어떤 extra/via
로 발동했는지"만 기록해 검증한다.
"""
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

# 화면 없는 환경에서도 PyQt6 import 가 가능하도록 offscreen 플랫폼 사용
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main  # noqa: E402


# ── 정규화(한/영·대소문자 무관) ────────────────────────────────────
class TestNormalize(unittest.TestCase):
    def test_case_insensitive(self):
        self.assertEqual(main.normalize_keyseq("abc"),
                         main.normalize_keyseq("ABC"))
        self.assertEqual(main.normalize_keyseq("AbC"), "abc")

    def test_english_trigger_in_korean_mode(self):
        # 영문 "abc" 키를 한글 모드로 치면 ㅁ,ㅠ,ㅊ 자모가 들어온다.
        self.assertEqual(main.normalize_keyseq("abc"),
                         main.normalize_keyseq("ㅁㅠㅊ"))
        # 그 자모들이 조합된 완성형 "뮻" 도 같은 키로 정규화된다.
        self.assertEqual(main.normalize_keyseq("abc"),
                         main.normalize_keyseq("뮻"))

    def test_korean_trigger_in_english_mode(self):
        # "안녕" 을 영문 모드로 치면 dkssud 키가 된다.
        self.assertEqual(main.normalize_keyseq("안녕"),
                         main.normalize_keyseq("dkssud"))

    def test_special_shortcut_in_korean_mode(self):
        # ";date" 의 date 키를 한글로 치면 ㅇ,ㅁ,ㅅ,ㄷ (d,a,t,e 위치).
        self.assertEqual(main.normalize_keyseq(";date"),
                         main.normalize_keyseq(";ㅇㅁㅅㄷ"))

    def test_double_consonant_is_case_insensitive(self):
        # 된소리 ㅃ(shift+ㅂ)은 평음 키 q 로 정규화 → ㅂ 과 같다.
        self.assertEqual(main.normalize_keyseq("ㅃ"),
                         main.normalize_keyseq("ㅂ"))
        self.assertEqual(main.normalize_keyseq("ㅃ"), "q")

    def test_compound_jamo_in_syllable(self):
        # 왔 = ㅇ(d) + ㅘ(h,k) + ㅆ(t) → "dhkt"
        self.assertEqual(main.normalize_keyseq("왔"), "dhkt")

    def test_digits_and_symbols_passthrough(self):
        self.assertEqual(main.normalize_keyseq("12!#"), "12!#")


# ── 한글 자모 조합 ─────────────────────────────────────────────────
class TestComposeHangul(unittest.TestCase):
    def test_basic_syllable(self):
        self.assertEqual(main.compose_hangul("ㅇㅏㄴ"), "안")

    def test_jong_moves_to_next_syllable(self):
        # "간" + ㅏ → 받침 ㄴ 이 다음 음절 초성으로 → "가나"
        self.assertEqual(main.compose_hangul("ㄱㅏㄴㅏ"), "가나")

    def test_non_hangul_passthrough(self):
        self.assertEqual(main.compose_hangul("abc1"), "abc1")


# ── 출력 변수 치환 ─────────────────────────────────────────────────
class TestResolveOutput(unittest.TestCase):
    def test_plain_text(self):
        self.assertEqual(main.resolve_output("hello"), "hello")

    def test_date_placeholder_format(self):
        out = main.resolve_output("{date:%Y}")
        self.assertEqual(len(out), 4)
        self.assertTrue(out.isdigit())

    def test_invalid_format_kept(self):
        # 미해석(정의 안 된) 키는 원본을 보존
        self.assertEqual(main.resolve_output("{nope}"), "{nope}")

    # ── 위치 인자 ──────────────────────────────────────────────
    def test_positional_args(self):
        self.assertEqual(
            main.resolve_output("{1} {2}", args=["가", "나"]), "가 나")

    def test_positional_arg_missing_is_empty(self):
        self.assertEqual(main.resolve_output("[{1}]", args=[]), "[]")

    def test_positional_arg_default(self):
        # 인자가 없으면 콜론 뒤 기본값 사용
        self.assertEqual(main.resolve_output("{1:없음}", args=[]), "없음")
        # 인자가 있으면 기본값 무시
        self.assertEqual(main.resolve_output("{1:없음}", args=["값"]), "값")

    def test_star_all_args_preserves_spaces(self):
        self.assertEqual(
            main.resolve_output("{*}", args=["a", "b"], args_all="a  b"),
            "a  b")

    def test_star_defaults_to_joined_args(self):
        self.assertEqual(main.resolve_output("{*}", args=["a", "b"]), "a b")

    # ── 재사용 변수 ────────────────────────────────────────────
    def test_variable_substitution(self):
        self.assertEqual(
            main.resolve_output("{회사} 드림", variables={"회사": "한빛"}),
            "한빛 드림")

    def test_unknown_variable_kept(self):
        self.assertEqual(main.resolve_output("{없는변수}"), "{없는변수}")

    def test_mixed_date_arg_variable(self):
        out = main.resolve_output(
            "{회사} {1} {date:%Y}", args=["홍길동"], variables={"회사": "한빛"})
        self.assertTrue(out.startswith("한빛 홍길동 "))

    # ── 이스케이프 ─────────────────────────────────────────────
    def test_literal_braces(self):
        self.assertEqual(main.resolve_output("{{1}}"), "{1}")
        self.assertEqual(
            main.resolve_output("{{회사}}", variables={"회사": "한빛"}),
            "{회사}")

    def test_backward_compatible_no_args(self):
        # args/variables 를 안 넘기면 날짜/시간만 처리(기존 동작)
        self.assertEqual(main.resolve_output("plain {1}"), "plain ")


# ── 파라미터 규칙 감지 & 변수명 검증 ───────────────────────────────
class TestParamDetectionAndVarNames(unittest.TestCase):
    def test_output_is_parameterized(self):
        self.assertTrue(main.output_is_parameterized("{1}"))
        self.assertTrue(main.output_is_parameterized("hi {2} there"))
        self.assertTrue(main.output_is_parameterized("{*}"))
        self.assertTrue(main.output_is_parameterized("{1:기본}"))

    def test_not_parameterized(self):
        self.assertFalse(main.output_is_parameterized("{date}"))
        self.assertFalse(main.output_is_parameterized("{회사}"))
        self.assertFalse(main.output_is_parameterized("plain"))
        # 이스케이프된 중괄호는 인자가 아님
        self.assertFalse(main.output_is_parameterized("{{1}}"))

    def test_valid_variable_names(self):
        for name in ("회사", "name", "user_id", "a1"):
            self.assertEqual(main.validate_variable_name(name), "")

    def test_invalid_variable_names(self):
        for name in ("", "123", "*", "date", "time", "datetime", "a:b", "x{y"):
            self.assertNotEqual(main.validate_variable_name(name), "")


# ── ';;' 우선 정렬 ─────────────────────────────────────────────────
class TestPrioritizeRules(unittest.TestCase):
    def _r(self, trig):
        return {"type": "special", "trigger": trig, "output": "x", "enabled": True}

    def test_double_semicolon_floats_to_top(self):
        rules = [self._r("abc"), self._r(";;d"), self._r("efg"), self._r(";;z")]
        ordered = main.prioritize_rules(rules)
        self.assertEqual([r["trigger"] for r in ordered],
                         [";;d", ";;z", "abc", "efg"])

    def test_stable_within_groups(self):
        # 같은 그룹(;; 끼리 / 나머지끼리) 내부 상대 순서는 유지
        rules = [self._r(";;b"), self._r(";;a"), self._r("c"), self._r("b")]
        ordered = main.prioritize_rules(rules)
        self.assertEqual([r["trigger"] for r in ordered],
                         [";;b", ";;a", "c", "b"])

    def test_no_double_semicolon_unchanged(self):
        rules = [self._r("a"), self._r(";b"), self._r("c")]
        ordered = main.prioritize_rules(rules)
        self.assertEqual([r["trigger"] for r in ordered], ["a", ";b", "c"])


# ── 리스너 매칭 (가짜 치환으로 발동 내역만 검증) ───────────────────
class ListenerHarness:
    """KeyboardListener 를 감싸 실제 키 주입 없이 발동 내역만 기록."""

    def __init__(self, rules):
        self.listener = main.KeyboardListener()
        self.events = []
        self.listener._do_replace = self._fake_replace
        self.listener._do_replace_norm = self._fake_replace_norm
        self.listener.set_rules(rules)

    def _fake_replace(self, trigger, output, extra="", via="composed",
                      **kwargs):
        self.events.append(("fire", trigger, extra, via))
        self.listener.buffer = main.resolve_output(output) + extra
        self.listener.composed = main.compose_hangul(self.listener.buffer)

    def _fake_replace_norm(self, trigger, output, k, extra=""):
        self.events.append(("norm", trigger, extra, "norm"))
        self.listener.buffer = main.resolve_output(output) + extra
        self.listener.composed = main.compose_hangul(self.listener.buffer)

    def type_chars(self, s):
        for ch in s:
            self.listener.buffer += ch
            self.listener.composed = main.compose_hangul(self.listener.buffer)
            self.listener._check_immediate()

    def press_space(self):
        self.listener._check_and_replace(append=" ")

    def press_enter(self):
        self.listener._check_and_replace(append="\n")

    def reset(self):
        self.listener.buffer = ""
        self.listener.composed = ""
        self.listener._pending = None
        self.events.clear()


class TestListenerMatching(unittest.TestCase):
    def test_special_exact(self):
        h = ListenerHarness([
            {"type": "special", "trigger": ";date", "output": "X", "enabled": True}])
        h.type_chars(";date")
        self.assertEqual([(e[0], e[1]) for e in h.events], [("fire", ";date")])

    def test_word_fires_on_space(self):
        h = ListenerHarness([
            {"type": "word", "trigger": "abc", "output": "123", "enabled": True}])
        h.type_chars("abc")
        self.assertEqual(h.events, [])  # 스페이스 전에는 발동 안 함
        h.press_space()
        self.assertEqual([(e[0], e[1], e[2]) for e in h.events],
                         [("fire", "abc", " ")])

    def test_normalize_cross_mode_word(self):
        h = ListenerHarness([
            {"type": "word", "trigger": "abc", "output": "123", "enabled": True}])
        # 한글 모드로 같은 키(ㅁㅠㅊ) → 정규화 매칭
        h.type_chars("ㅁㅠㅊ")
        h.press_space()
        self.assertTrue(any(e[0] == "norm" and e[1] == "abc" for e in h.events))

    def test_normalize_uppercase(self):
        h = ListenerHarness([
            {"type": "word", "trigger": "abc", "output": "123", "enabled": True}])
        h.type_chars("ABC")
        h.press_space()
        self.assertTrue(any(e[1] == "abc" for e in h.events))

    def test_normalize_off_no_cross_mode(self):
        h = ListenerHarness([
            {"type": "word", "trigger": "abc", "output": "123", "enabled": True}])
        h.listener.set_normalize_mode(False)
        h.type_chars("ㅁㅠㅊ")
        h.press_space()
        self.assertEqual(h.events, [])

    def test_regex_on_space(self):
        h = ListenerHarness([
            {"type": "regex", "trigger": r"\d{4}", "output": "[Y]", "enabled": True}])
        h.type_chars("2026")
        h.press_space()
        self.assertEqual([(e[0], e[1]) for e in h.events], [("fire", "2026")])


class TestPrefixCollision(unittest.TestCase):
    """접두사가 겹치는 special 트리거(::d / ::dev) 둘 다 사용 가능 검증."""

    def _harness(self):
        return ListenerHarness([
            {"type": "special", "trigger": "::d", "output": "DELTA", "enabled": True},
            {"type": "special", "trigger": "::dev", "output": "DEVELOP", "enabled": True},
        ])

    def test_longer_trigger_wins(self):
        h = self._harness()
        h.type_chars("::dev")
        self.assertEqual([(e[1], e[3]) for e in h.events], [("::dev", "composed")])

    def test_shorter_confirmed_on_space(self):
        h = self._harness()
        h.type_chars("::d")
        self.assertEqual(h.events, [])  # 보류 중
        self.assertIsNotNone(h.listener._pending)
        h.press_space()
        self.assertEqual([(e[1], e[2]) for e in h.events], [("::d", " ")])

    def test_shorter_confirmed_on_enter(self):
        h = self._harness()
        h.type_chars("::d")
        h.press_enter()
        self.assertEqual([(e[1], e[2]) for e in h.events], [("::d", "\n")])

    def test_shorter_confirmed_with_breaking_char(self):
        h = self._harness()
        # ::d 후 라이벌(::dev)로 갈 수 없는 'x' → ::d 확정 + x 보존
        h.type_chars("::dx")
        self.assertEqual([(e[1], e[2]) for e in h.events], [("::d", "x")])

    def test_step_by_step_to_longer(self):
        h = self._harness()
        h.type_chars("::de")  # 아직 보류(라이벌 도달 가능)
        self.assertEqual(h.events, [])
        h.type_chars("v")     # 완성
        self.assertEqual([(e[1],) for e in h.events], [("::dev",)])

    def test_no_rival_fires_immediately(self):
        h = ListenerHarness([
            {"type": "special", "trigger": "::d", "output": "DELTA", "enabled": True}])
        h.type_chars("::d")
        self.assertEqual([(e[1],) for e in h.events], [("::d",)])


# ── 치환(텍스트 변환) 중 사용자 입력 무시 ─────────────────────────
class _FakeCharKey:
    """pynput 의 char 키를 흉내내는 가짜 키 (key.char 만 제공)."""
    def __init__(self, c):
        self.char = c


class TestIgnoreInputWhileReplacing(unittest.TestCase):
    def _listener(self):
        L = main.KeyboardListener()
        L.set_rules([
            {"type": "word", "trigger": "abc", "output": "123", "enabled": True}])
        return L

    def test_char_ignored_while_replacing(self):
        L = self._listener()
        L._replacing = True
        L._on_press(_FakeCharKey("a"))
        self.assertEqual(L.buffer, "")  # 변환 중 → 입력 무시
        # 변환이 끝나면(_replacing False) 정상 처리
        L._replacing = False
        L._on_press(_FakeCharKey("a"))
        self.assertEqual(L.buffer, "a")

    def test_space_enter_ignored_while_replacing(self):
        L = self._listener()
        L.buffer = "abc"
        L.composed = "abc"
        L._replacing = True
        # 변환 중 스페이스/엔터는 무시 → 버퍼 변화 없음, 치환도 안 일어남
        L._on_press(main.Key.space)
        L._on_press(main.Key.enter)
        self.assertEqual(L.buffer, "abc")

    def test_char_ignored_while_suppressed(self):
        import time
        L = self._listener()
        L._suppress_until = time.monotonic() + 5
        L._on_press(_FakeCharKey("a"))
        self.assertEqual(L.buffer, "")


# ── 디버그 로깅 on/off ─────────────────────────────────────────────
class TestDebugLog(unittest.TestCase):
    def setUp(self):
        self._old_file = main.DEBUG_LOG_FILE
        self._old_env = os.environ.pop("KEYFLUX_DEBUG", None)
        self._tmp = Path(tempfile.gettempdir()) / f"kf_dbg_test_{os.getpid()}.log"
        if self._tmp.exists():
            self._tmp.unlink()
        main.DEBUG_LOG_FILE = self._tmp

    def tearDown(self):
        main.set_debug(False)
        main.DEBUG_LOG_FILE = self._old_file
        if self._old_env is not None:
            os.environ["KEYFLUX_DEBUG"] = self._old_env
        if self._tmp.exists():
            self._tmp.unlink()

    def test_logs_when_enabled(self):
        main.set_debug(True)
        main.dbg("hello-debug")
        self.assertTrue(self._tmp.exists())
        self.assertIn("hello-debug", self._tmp.read_text(encoding="utf-8"))

    def test_silent_when_disabled(self):
        main.set_debug(False)
        main.dbg("should-not-appear")
        # 꺼져 있으면 파일을 만들지 않거나, 만들어도 내용이 없어야 함
        if self._tmp.exists():
            self.assertNotIn("should-not-appear",
                             self._tmp.read_text(encoding="utf-8"))


# ── 진단 헬퍼 스모크 (예외 없이 동작하는지) ───────────────────────
class TestDiagnosticsSmoke(unittest.TestCase):
    def test_foreground_window_info_returns_str(self):
        self.assertIsInstance(main.foreground_window_info(), str)

    def test_is_startup_enabled_returns_bool(self):
        # 작업 스케줄러를 변경하지 않고 조회만 — 항상 bool 반환
        self.assertIsInstance(main.is_startup_enabled(), bool)

    def test_is_elevated_returns_bool(self):
        # 관리자 권한 여부 조회 — 항상 bool 반환(예외 없이)
        self.assertIsInstance(main.is_elevated(), bool)

    def test_startup_target_command_nonempty(self):
        if sys.platform == "win32":
            self.assertTrue(main._startup_target_command())


# ── 결과 대소문자 보장 옵션 ────────────────────────────────────────
class TestCaseGuaranteeOption(unittest.TestCase):
    def test_default_setting_on(self):
        # 기본값은 전부 켜짐 — 결과 대소문자 보장도 기본 True
        self.assertTrue(main.DEFAULT_SETTINGS["output_case_guarantee"])

    def test_listener_default_on(self):
        L = main.KeyboardListener()
        self.assertTrue(L.case_guarantee)

    def test_setter_toggles(self):
        L = main.KeyboardListener()
        L.set_case_guarantee(False)
        self.assertFalse(L.case_guarantee)
        L.set_case_guarantee(True)
        self.assertTrue(L.case_guarantee)

    def test_send_text_accepts_case_guarantee(self):
        # 빈 문자열은 어느 플랫폼에서든 예외 없이 True 반환(시그니처 검증)
        self.assertTrue(main.send_text("", case_guarantee=True))
        self.assertTrue(main.send_text("", case_guarantee=False))


# ── 주입 방식 선택 (콘솔=스캔코드 / 그 외=유니코드) ────────────────
class TestInjectionMethodSelection(unittest.TestCase):
    """대상 창 종류에 따라 스캔코드/유니코드 주입을 고르는 로직 검증.
    (#2 VSCode 터미널 미입력 · #1 입력 언어 보존의 핵심 분기)"""

    def test_foreground_needs_scancode_returns_bool(self):
        # 실제 포그라운드 창을 조회하지만 항상 bool 을 반환해야 한다.
        self.assertIsInstance(main.foreground_needs_scancode(), bool)

    def test_send_text_accepts_force_unicode(self):
        # 빈 문자열은 어느 플랫폼에서든 예외 없이 True (시그니처 검증)
        self.assertTrue(main.send_text("", force_unicode=True))
        self.assertTrue(main.send_text("", force_unicode=False))

    @unittest.skipUnless(sys.platform == "win32", "win32 전용 상수")
    def test_console_classes_use_scancode(self):
        # 사용자가 검증한 콘솔(PowerShell/cmd/Windows Terminal/Git Bash 등)은
        # 반드시 스캔코드 화이트리스트에 들어 있어야 IME 강제·복원 경로를 탄다.
        for cls in ("ConsoleWindowClass",            # conhost: powershell.exe·cmd.exe
                    "CASCADIA_HOSTING_WINDOW_CLASS",  # Windows Terminal
                    "mintty",                         # Git Bash
                    "VirtualConsoleClass"):           # ConEmu·Cmder
            self.assertIn(cls, main._SCANCODE_WINDOW_CLASSES)

    @unittest.skipUnless(sys.platform == "win32", "win32 전용 상수")
    def test_gui_and_chromium_use_unicode(self):
        # VSCode 등 Electron/Chromium(Chrome_WidgetWin_1)과 일반 GUI 는
        # 스캔코드 화이트리스트에 없어야 한다 → 유니코드 직접 주입 경로.
        for cls in ("Chrome_WidgetWin_1",  # VSCode·Electron·Chrome
                    "Notepad",             # 일반 Win32 GUI
                    "Qt5152QWindowIcon",   # 임의 Qt 앱
                    ""):                   # 알 수 없음 → 유니코드 기본
            self.assertNotIn(cls, main._SCANCODE_WINDOW_CLASSES)


# ── 규칙 추가 다이얼로그: 타입 순서/저장 (단축어 1순위) ─────────────
class TestRuleDialogTypeOrder(unittest.TestCase):
    """규칙 추가 시 special(단축어)이 1순위·기본 선택이고, 각 타입이
    올바른 콤보 인덱스로 저장/복원되는지 검증."""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_special_is_first_item(self):
        d = main.RuleDialog()
        self.assertTrue(d.type_combo.itemText(0).startswith("special"))

    def test_new_rule_default_is_special(self):
        # 신규 추가(규칙 미지정) 시 기본 선택 타입이 special 이어야 한다.
        d = main.RuleDialog()
        self.assertEqual(d.get_rule()["type"], "special")

    def test_type_roundtrip(self):
        # 각 타입을 로드하면 올바른 인덱스로 복원되고, 저장 시 같은 타입이 나온다.
        for t in ("special", "word", "regex"):
            d = main.RuleDialog(
                rule={"type": t, "trigger": "x", "output": "y", "enabled": True})
            self.assertEqual(d.get_rule()["type"], t)


# ── 규칙 다이얼로그: 출력에 줄바꿈(Enter) 포함 저장 ────────────────
class TestRuleDialogMultilineOutput(unittest.TestCase):
    """출력 필드가 다중 줄이 되어, Enter(줄바꿈)를 담은 출력을 저장하면
    앞뒤 줄바꿈까지 그대로 보존되는지 검증(트리거는 여전히 strip)."""

    @classmethod
    def setUpClass(cls):
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_multiline_output_roundtrip(self):
        d = main.RuleDialog(rule={
            "type": "word", "trigger": "sig",
            "output": "line1\nline2\n", "enabled": True})
        r = d.get_rule()
        self.assertEqual(r["output"], "line1\nline2\n")  # 후행 줄바꿈까지 보존
        self.assertEqual(r["trigger"], "sig")

    def test_output_not_stripped(self):
        # 앞뒤 공백/줄바꿈이 있는 출력은 그대로 저장(strip 하지 않음).
        d = main.RuleDialog(rule={
            "type": "word", "trigger": "t",
            "output": "\n  hi  \n", "enabled": True})
        self.assertEqual(d.get_rule()["output"], "\n  hi  \n")

    def test_trigger_still_stripped(self):
        d = main.RuleDialog(rule={
            "type": "word", "trigger": "  ab ",
            "output": "x", "enabled": True})
        self.assertEqual(d.get_rule()["trigger"], "ab")


# ── 문장 중간에서 단축어 사용 시 앞 문맥(띄어쓰기/글자) 보존 ───────
def _jamo_seq(word):
    """완성형 한글 문자열을 사용자가 실제 누르는 자모 시퀀스로 분해."""
    CHO = list("ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ")
    JUNG = list("ㅏㅐㅑㅒㅓㅔㅕㅖㅗㅘㅙㅚㅛㅜㅝㅞㅟㅠㅡㅢㅣ")
    JONG = [""] + list("ㄱㄲㄳㄴㄵㄶㄷㄹㄺㄻㄼㄽㄾㄿㅀㅁㅂㅄㅅㅆㅇㅈㅊㅋㅌㅍㅎ")
    out = ""
    for ch in word:
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            c = o - 0xAC00
            ci, rem = divmod(c, 21 * 28)
            vi, ji = divmod(rem, 28)
            out += CHO[ci] + JUNG[vi] + (JONG[ji] if ji else "")
        else:
            out += ch
    return out


class _ScreenSim:
    """실제 _do_replace 를 태우되 주입 대신 (backspace 수, 주입 텍스트)만
    잡아, '화면'을 compose_hangul(raw) 로 재구성해 치환 후 화면을 계산한다."""

    def __init__(self, rule, normalize=True):
        self.L = main.KeyboardListener()
        self.L.set_normalize_mode(normalize)
        self.L.set_rules([rule])
        self.cap = {}

        def fake_inject(trigger, to_type, resolved, bs, composing=False):
            self.cap.update(to_type=to_type, bs=bs, composing=composing)
            self.L._replacing = False

        self.L._inject_replacement = fake_inject
        self.raw = ""

    def type_jamo(self, s):
        for ch in _jamo_seq(s):
            self.raw += ch
            self.L._on_press(_FakeCharKeyLike(ch))
        return self

    def finish(self, key):
        self.raw += " " if key == "space" else "\n"
        self.L._on_press(main.Key.space if key == "space" else main.Key.enter)
        return self

    def screen_after(self):
        before = main.compose_hangul(self.raw)
        if "bs" not in self.cap:
            return None  # 발동 안 함
        bs = self.cap["bs"]
        head = before[:-bs] if bs <= len(before) else "@UNDERFLOW@"
        return head + self.cap["to_type"]


class _FakeCharKeyLike:
    def __init__(self, c):
        self.char = c


class TestPrecedingContextPreserved(unittest.TestCase):
    """문장 맨 앞이 아닌 위치에서 단축어를 써도 앞의 글자/띄어쓰기가
    사라지지 않아야 한다(조합 경계 병합 과다삭제 버그 회귀 방지)."""

    def test_space_preserved_word_english(self):
        s = _ScreenSim({"type": "word", "trigger": "abc",
                        "output": "OUT", "enabled": True})
        s.type_jamo("hi ").type_jamo("abc").finish("space")
        self.assertEqual(s.screen_after(), "hi OUT ")

    def test_space_preserved_special_korean(self):
        s = _ScreenSim({"type": "special", "trigger": ";;안녕",
                        "output": "OUT", "enabled": True})
        s.type_jamo("테스트 ").type_jamo(";;안녕")
        self.assertEqual(s.screen_after(), "테스트 OUT")

    def test_space_preserved_cross_mode(self):
        # 한글모드로 영문 트리거(abc) 입력(ㅁㅠㅊ→뮻), 앞 문맥 보존
        s = _ScreenSim({"type": "word", "trigger": "abc",
                        "output": "OUT", "enabled": True})
        s.type_jamo("안녕 ").type_jamo("ㅁㅠㅊ").finish("space")
        self.assertEqual(s.screen_after(), "안녕 OUT ")

    def test_boundary_merge_preserves_preceding_char(self):
        # 앞 글자 "가"(받침 없음) 뒤에 첫 자음이 받침으로 합쳐지는 트리거
        # "ㄴ;x" → 화면 "간;x". 종전엔 "가"까지 지워졌으나, 이제 복원돼야 함.
        s = _ScreenSim({"type": "special", "trigger": "ㄴ;x",
                        "output": "OUT", "enabled": True})
        s.type_jamo("가").type_jamo("ㄴ;x")
        self.assertEqual(s.screen_after(), "가OUT")

    def test_boundary_merge_with_space_unaffected(self):
        # 앞에 공백이 있으면 병합이 없으므로 그대로 정상
        s = _ScreenSim({"type": "special", "trigger": "ㄴ;x",
                        "output": "OUT", "enabled": True})
        s.type_jamo("가 ").type_jamo("ㄴ;x")
        self.assertEqual(s.screen_after(), "가 OUT")

    def test_shortcut_at_start_still_works(self):
        s = _ScreenSim({"type": "special", "trigger": ";date",
                        "output": "OUT", "enabled": True})
        s.type_jamo(";date")
        self.assertEqual(s.screen_after(), "OUT")


# ── 인라인 인자 캡처(파라미터 규칙) 통합 ─────────────────────────
class TestInlineArgCapture(unittest.TestCase):
    """파라미터 규칙: 트리거 뒤 공백으로 인자 입력 → Enter 확정 → 치환.
    실제 _do_replace 를 태워 화면(스크린 모델) 결과를 검증한다."""

    def _sim(self, output, normalize=True):
        return _ScreenSim({"type": "special", "trigger": ";메일",
                           "output": output, "enabled": True}, normalize)

    def test_positional_arg_capture(self):
        s = self._sim("{1} 님께")
        s.type_jamo(";메일").type_jamo(" 홍길동").finish("enter")
        self.assertEqual(s.screen_after(), "홍길동 님께")

    def test_capture_preserves_preceding_context(self):
        s = self._sim("{1} 님께")
        s.type_jamo("안녕 ").type_jamo(";메일").type_jamo(" 홍길동").finish("enter")
        self.assertEqual(s.screen_after(), "안녕 홍길동 님께")

    def test_star_captures_all_args(self):
        s = self._sim("[{*}]")
        s.type_jamo(";메일").type_jamo(" a b c").finish("enter")
        self.assertEqual(s.screen_after(), "[a b c]")

    def test_multiple_positional_args(self):
        s = self._sim("{2}-{1}")
        s.type_jamo(";메일").type_jamo(" a b").finish("enter")
        self.assertEqual(s.screen_after(), "b-a")

    def test_empty_args_enter_immediately_uses_default(self):
        s = self._sim("{1:없음}")
        s.type_jamo(";메일").finish("enter")
        self.assertEqual(s.screen_after(), "없음")

    def test_variable_in_capture_output(self):
        s = self._sim("{회사} {1} 드림")
        s.L.set_variables({"회사": "한빛"})
        s.type_jamo(";메일").type_jamo(" 홍길동").finish("enter")
        self.assertEqual(s.screen_after(), "한빛 홍길동 드림")


class TestVariableInStaticRule(unittest.TestCase):
    """파라미터가 없는 일반 규칙이라도 {이름} 변수는 즉시 치환된다."""

    def test_static_variable_substitution(self):
        s = _ScreenSim({"type": "special", "trigger": ";회사",
                        "output": "{회사}", "enabled": True})
        s.L.set_variables({"회사": "한빛"})
        s.type_jamo(";회사")
        self.assertEqual(s.screen_after(), "한빛")


class TestCaptureStateMachine(unittest.TestCase):
    """캡처 진입/취소 등 상태 전이 검증(주입은 가짜로 대체)."""

    def _L(self, output="{1}"):
        L = main.KeyboardListener()
        L._inject_replacement = lambda *a, **k: setattr(L, "_replacing", False)
        L.set_rules([{"type": "special", "trigger": ";x",
                      "output": output, "enabled": True}])
        return L

    def _type(self, L, s):
        for ch in s:
            L._on_press(_FakeCharKey(ch))

    def test_enters_capture_on_param_trigger(self):
        L = self._L("{1}")
        self._type(L, ";x")
        self.assertIsNotNone(L._capturing)

    def test_no_capture_for_static_trigger(self):
        L = self._L("정적출력")
        self._type(L, ";x")
        self.assertIsNone(L._capturing)

    def test_backspace_past_trigger_cancels(self):
        L = self._L("{1}")
        self._type(L, ";x")
        L._on_press(main.Key.backspace)  # 트리거 밖으로 지움 → 취소
        self.assertIsNone(L._capturing)

    def test_esc_cancels_capture(self):
        L = self._L("{1}")
        self._type(L, ";x")
        L._on_press(main.Key.esc)
        self.assertIsNone(L._capturing)

    def test_args_too_long_cancels(self):
        L = self._L("{1}")
        self._type(L, ";x")
        self._type(L, "a" * (L._CAPTURE_MAX_ARGS + 5))
        self.assertIsNone(L._capturing)

    def test_deactivate_clears_capture(self):
        L = self._L("{1}")
        self._type(L, ";x")
        L.set_active(False)
        self.assertIsNone(L._capturing)


# ── 변환(치환) 중 사용자 실입력 전역 차단 판단 ────────────────────
class _FakeHookData:
    """pynput 저수준 후크의 _KBDLLHOOKSTRUCT 를 흉내내는 가짜 데이터."""
    def __init__(self, flags, vk=8, scan=0):
        self.flags = flags
        self.vkCode = vk
        self.scanCode = scan


class TestBlockingDuringReplace(unittest.TestCase):
    """_blocking_now: '변환 진행 중 + 사용자 실입력' 일 때만 True.
    (한/영·Enter·Backspace 등을 변환 중에만 전역 차단하는 판단 로직)"""

    def _listener(self):
        L = main.KeyboardListener()
        L.active = True
        L._replacing = False
        L._suppress_until = 0.0
        return L

    def test_block_user_key_while_replacing(self):
        L = self._listener()
        L._replacing = True
        self.assertTrue(L._blocking_now(_FakeHookData(0x00)))

    def test_pass_injected_event_while_replacing(self):
        # 우리 주입 이벤트(LLKHF_INJECTED)는 변환 중이라도 통과해야 치환이 진행됨
        L = self._listener()
        L._replacing = True
        inj = main.KeyboardListener._LLKHF_INJECTED
        self.assertFalse(L._blocking_now(_FakeHookData(inj)))

    def test_block_within_suppress_window(self):
        import time
        L = self._listener()
        L._suppress_until = time.monotonic() + 5
        self.assertTrue(L._blocking_now(_FakeHookData(0x00)))

    def test_no_block_when_idle(self):
        # 변환을 하지 않는 평상시엔 사용자 키도 차단하지 않음
        L = self._listener()
        self.assertFalse(L._blocking_now(_FakeHookData(0x00)))

    def test_no_block_when_inactive(self):
        L = self._listener()
        L._replacing = True
        L.active = False
        self.assertFalse(L._blocking_now(_FakeHookData(0x00)))

    def test_filter_suppresses_only_when_blocking(self):
        # win32_event_filter 는 차단 대상일 때만 suppress_event() 를 부른다.
        L = self._listener()
        calls = []

        class _StubListener:
            def suppress_event(self):
                calls.append(True)
                raise RuntimeError("suppressed")  # 실제 pynput 도 예외를 던짐

        L._listener = _StubListener()

        # 유휴 상태: 차단 안 함 → suppress_event 호출 없음, 정상 반환
        self.assertTrue(L._win32_event_filter(0x0100, _FakeHookData(0x00)))
        self.assertEqual(calls, [])

        # 변환 중 + 사용자 실입력: suppress_event 호출 → 예외 전파(차단)
        L._replacing = True
        with self.assertRaises(RuntimeError):
            L._win32_event_filter(0x0100, _FakeHookData(0x00))
        self.assertEqual(calls, [True])


# ── 차단한 사용자 키를 버리지 않고 되돌려주기 ──────────────────────
class _SuppressCalled(Exception):
    """pynput 의 suppress_event() 처럼 필터 실행을 중단시키는 신호."""


class _SuppressingListener:
    def __init__(self):
        self.suppressed = 0

    def suppress_event(self):
        self.suppressed += 1
        raise _SuppressCalled()


class TestBlockedKeysReplayed(unittest.TestCase):
    """단축어가 텍스트로 바뀌는 짧은 동안 사용자가 이어서 친 키(특히 뒤의
    띄어쓰기)도 전역 차단된다. 차단만 하고 버리면 그 글자는 화면에서 아예
    사라지므로, 차단분은 큐에 모아 두었다가 치환이 끝난 뒤 그대로 돌려줘야
    한다."""

    VK_SPACE = 0x20

    def _listener(self):
        L = main.KeyboardListener()
        L.set_rules([{"type": "special", "trigger": ";abc",
                      "output": "OUT", "enabled": True}])
        L._listener = _SuppressingListener()
        return L

    def test_blocked_key_is_queued_not_dropped(self):
        L = self._listener()
        L._replacing = True  # 치환 주입 중
        with self.assertRaises(_SuppressCalled):
            L._win32_event_filter(0x0100, _FakeHookData(0x00, vk=self.VK_SPACE,
                                                        scan=57))
        self.assertEqual(L._listener.suppressed, 1, "차단 자체는 그대로 한다")
        self.assertEqual(L._blocked_keys, [(self.VK_SPACE, 57, 0)],
                         "차단한 키는 버려지지 않고 큐에 남는다")

    def test_keyup_and_extended_flags_preserved(self):
        L = self._listener()
        L._replacing = True
        with self.assertRaises(_SuppressCalled):  # 뗌(keyup)
            L._win32_event_filter(0x0101, _FakeHookData(0x00, vk=self.VK_SPACE,
                                                        scan=57))
        with self.assertRaises(_SuppressCalled):  # 확장키(←)
            L._win32_event_filter(0x0100, _FakeHookData(0x01, vk=0x25, scan=75))
        self.assertEqual(L._blocked_keys, [
            (self.VK_SPACE, 57, main._KEYEVENTF_KEYUP),
            (0x25, 75, main._KEYEVENTF_EXTENDEDKEY),
        ], "눌림/뗌·확장키 여부까지 보존해야 원래대로 재생된다")

    def test_our_own_injected_keys_are_not_queued(self):
        L = self._listener()
        L._replacing = True
        inj = main.KeyboardListener._LLKHF_INJECTED
        L._win32_event_filter(0x0100, _FakeHookData(inj, vk=self.VK_SPACE))
        self.assertEqual(L._blocked_keys, [], "우리 주입분은 재생 대상이 아니다")

    def test_queue_is_capped(self):
        L = self._listener()
        L._replacing = True
        for _ in range(main.KeyboardListener._MAX_BLOCKED_KEYS + 20):
            with self.assertRaises(_SuppressCalled):
                L._win32_event_filter(0x0100, _FakeHookData(0x00,
                                                            vk=self.VK_SPACE))
        self.assertEqual(len(L._blocked_keys),
                         main.KeyboardListener._MAX_BLOCKED_KEYS,
                         "큐가 무한정 자라지 않는다")

    def test_replay_sends_queued_keys_and_lifts_suppression(self):
        L = self._listener()
        sent = []
        orig = main.send_key_events
        main.send_key_events = lambda events: (sent.extend(events), True)[1]
        try:
            L._suppress_until = time.monotonic() + 5
            L._blocked_keys = [(self.VK_SPACE, 57, 0)]
            L._replay_blocked_keys()
        finally:
            main.send_key_events = orig
        self.assertEqual(sent, [(self.VK_SPACE, 57, 0)], "차단분을 그대로 재전송")
        self.assertEqual(L._blocked_keys, [], "큐는 비워진다")
        self.assertLessEqual(L._suppress_until, time.monotonic(),
                             "재생분이 버퍼에도 반영되도록 억제를 먼저 푼다")

    def test_key_blocked_after_injection_is_still_replayed(self):
        """주입은 끝났지만 억제 시간이 조금 남은 구간에서 차단된 키도
        (되돌려줄 주입 스레드가 없으므로) 예약 타이머가 비워 줘야 한다."""
        L = self._listener()
        sent = []
        orig = main.send_key_events
        main.send_key_events = lambda events: (sent.extend(events), True)[1]
        try:
            L._replacing = False
            L._suppress_until = time.monotonic() + 0.05  # 억제 꼬리 구간
            with self.assertRaises(_SuppressCalled):
                L._win32_event_filter(0x0100, _FakeHookData(0x00,
                                                            vk=self.VK_SPACE,
                                                            scan=57))
            self.assertEqual(L._blocked_keys, [(self.VK_SPACE, 57, 0)])
            deadline = time.monotonic() + 5
            while sent == [] and time.monotonic() < deadline:
                time.sleep(0.01)
        finally:
            main.send_key_events = orig
        self.assertEqual(sent, [(self.VK_SPACE, 57, 0)],
                         "억제가 풀리는 시점에 차단분이 되돌아와야 한다")
        self.assertEqual(L._blocked_keys, [])

    def test_deactivate_drops_queued_keys(self):
        L = self._listener()
        L._blocked_keys = [(self.VK_SPACE, 57, 0)]
        L.set_active(False)
        self.assertEqual(L._blocked_keys, [],
                         "꺼진 뒤 엉뚱한 시점에 되돌려주지 않는다")

    def test_spaces_around_a_shortcut_survive(self):
        """문장 중간에서 "안녕 ;abc " 처럼 쓸 때, 단축어 앞의 띄어쓰기는
        물론 치환 도중 곧바로 친 뒤쪽 띄어쓰기까지 남아 "안녕 OUT " 이
        되어야 한다(종전엔 뒤쪽 스페이스가 통째로 사라졌음)."""
        L = self._listener()
        done = threading.Event()

        orig = main.send_key_events

        def fake_send(events):  # OS 역할: 재생된 키를 리스너에게 되돌린다
            for vk, _scan, flags in events:
                if flags & main._KEYEVENTF_KEYUP:
                    continue
                if vk == self.VK_SPACE:
                    L._on_press(main.Key.space)
            return True

        def fake_inject(trigger, to_type, resolved, bs, composing=False):
            # 주입이 도는 동안 사용자가 스페이스를 친다 → 후크가 차단
            try:
                try:
                    L._win32_event_filter(0x0100,
                                          _FakeHookData(0x00, vk=self.VK_SPACE,
                                                        scan=57))
                except _SuppressCalled:
                    pass
            finally:
                L._replacing = False
                L._replay_blocked_keys()
                done.set()

        L._inject_replacement = fake_inject
        main.send_key_events = fake_send
        try:
            for ch in "hi":                 # 앞 문맥
                L._on_press(_FakeCharKey(ch))
            L._on_press(main.Key.space)     # 단축어 앞의 띄어쓰기
            for ch in ";abc":
                L._on_press(_FakeCharKey(ch))
            self.assertTrue(done.wait(5), "주입 스레드가 끝나야 한다")
        finally:
            main.send_key_events = orig

        self.assertEqual(L._blocked_keys, [])
        self.assertEqual(L.buffer, "hi OUT ",
                         "단축어 앞뒤의 띄어쓰기가 모두 유지돼야 한다")
        self.assertEqual(L.composed, "hi OUT ")


# ── 로그인 시 자동 실행(작업 스케줄러) ─────────────────────────────
class TestStartupTaskXml(unittest.TestCase):
    """schtasks /SC ONLOGON 으로 만든 작업은 기본값이
    DisallowStartIfOnBatteries=true 라, 노트북을 배터리로 쓰면 로그인해도
    조용히 실행되지 않는다(= '자동 실행 켜놨는데 부팅 시 안 켜짐'의 원인).
    그래서 작업을 XML 로 만들고, 그 XML 이 필요한 값을 담고 있는지 검증한다."""

    def test_battery_restrictions_are_off(self):
        xml = main._startup_task_xml()
        self.assertIn("<DisallowStartIfOnBatteries>false", xml)
        self.assertIn("<StopIfGoingOnBatteries>false", xml)

    def test_no_execution_time_limit(self):
        # 상주 프로그램이 기본 72시간 뒤 강제 종료되지 않도록 무제한
        self.assertIn("<ExecutionTimeLimit>PT0S</ExecutionTimeLimit>",
                      main._startup_task_xml())

    def test_runs_elevated_in_user_session(self):
        xml = main._startup_task_xml()
        self.assertIn("<RunLevel>HighestAvailable</RunLevel>", xml)
        self.assertIn("<LogonType>InteractiveToken</LogonType>", xml)
        self.assertIn("<LogonTrigger>", xml)

    def test_command_matches_current_target(self):
        exe, args = main._startup_target_parts()
        xml = main._startup_task_xml()
        self.assertIn(f"<Command>{exe}</Command>", xml)
        if args:
            self.assertIn("<Arguments>", xml)

    def test_xml_escapes_special_chars(self):
        real = main._startup_target_parts
        main._startup_target_parts = lambda: (r"C:\a&b\App.exe", "<x>")
        try:
            xml = main._startup_task_xml()
        finally:
            main._startup_target_parts = real
        self.assertIn("C:\\a&amp;b\\App.exe", xml)
        self.assertIn("&lt;x&gt;", xml)


class TestSetStartupFallbacks(unittest.TestCase):
    """등록은 XML → /SC ONLOGON → 레지스트리 Run 순으로 시도하고,
    실패 사유를 남겨 사용자에게 보여줄 수 있어야 한다."""

    def setUp(self):
        self._run = main._run_quiet
        self._reg = main._set_run_entry
        self.calls = []
        self.reg_calls = []
        main._set_run_entry = lambda enabled: (self.reg_calls.append(enabled),
                                               True)[1]

    def tearDown(self):
        main._run_quiet = self._run
        main._set_run_entry = self._reg

    def _fake_run(self, results):
        """results: 명령의 특징 문자열 → (rc, err) 매핑."""
        def run(cmd):
            self.calls.append(cmd)
            key = "xml" if "/XML" in cmd else (
                "create" if "/Create" in cmd else
                "delete" if "/Delete" in cmd else "query")
            return results.get(key, (0, ""))
        return run

    def test_xml_path_is_preferred(self):
        main._run_quiet = self._fake_run({})
        self.assertTrue(main.set_startup(True))
        self.assertTrue(any("/XML" in c for c in self.calls),
                        "먼저 XML 로 등록을 시도한다")
        self.assertNotIn("/SC", [a for c in self.calls for a in c],
                         "XML 이 성공하면 구형 방식은 쓰지 않는다")
        self.assertEqual(self.reg_calls, [False],
                         "작업 등록에 성공하면 Run 항목은 지운다(중복 실행 방지)")

    def test_falls_back_to_onlogon_then_run(self):
        main._run_quiet = self._fake_run({"xml": (1, "XML 거부"),
                                          "create": (1, "권한 없음")})
        self.assertTrue(main.set_startup(True), "최후엔 Run 으로라도 등록한다")
        self.assertTrue(any("/XML" in c for c in self.calls))
        self.assertTrue(any("/SC" in c for c in self.calls))
        self.assertIn(True, self.reg_calls, "Run 폴백까지 갔다")
        self.assertTrue(main.startup_last_error(), "실패 사유가 남는다")

    def test_all_paths_fail(self):
        main._run_quiet = self._fake_run({"xml": (1, "e1"), "create": (1, "e2")})
        main._set_run_entry = lambda enabled: False
        self.assertFalse(main.set_startup(True))
        self.assertTrue(main.startup_last_error())

    def test_disable_removes_task_and_run_entry(self):
        main._run_quiet = self._fake_run({})
        self.assertTrue(main.set_startup(False))
        self.assertTrue(any("/Delete" in c for c in self.calls))
        self.assertEqual(self.reg_calls, [False])


class TestStartupSelfHealing(unittest.TestCase):
    """설정이 '자동 실행 켬'인데 실제 등록이 없거나 낡은 경로를 가리키면,
    앱을 켤 때 조용히 다시 등록해야 한다. (작업이 지워졌거나 새 버전 exe 로
    갈아탄 경우 사용자는 계속 '켜져 있다'고 보면서 부팅 때만 안 뜬다)"""

    def setUp(self):
        self._state = main.startup_state
        self._set = main.set_startup
        self.registered = []
        main.set_startup = lambda v: (self.registered.append(v), True)[1]

    def tearDown(self):
        main.startup_state = self._state
        main.set_startup = self._set

    def _state_is(self, **kw):
        base = {"registered": True, "kind": "task", "command": "x",
                "stale": False}
        base.update(kw)
        main.startup_state = lambda: base

    def test_reregisters_when_task_is_missing(self):
        self._state_is(registered=False, kind=None, command=None)
        self.assertTrue(main.ensure_startup({"startup": True}))
        self.assertEqual(self.registered, [True])

    def test_reregisters_when_path_is_stale(self):
        self._state_is(stale=True)
        self.assertTrue(main.ensure_startup({"startup": True}))
        self.assertEqual(self.registered, [True])

    def test_upgrades_run_fallback_to_task(self):
        self._state_is(kind="run")
        self.assertTrue(main.ensure_startup({"startup": True}))

    def test_noop_when_healthy(self):
        self._state_is()
        self.assertFalse(main.ensure_startup({"startup": True}))
        self.assertEqual(self.registered, [])

    def test_noop_when_setting_off(self):
        self._state_is(registered=False)
        self.assertFalse(main.ensure_startup({"startup": False}))
        self.assertFalse(main.ensure_startup({}))
        self.assertEqual(self.registered, [])

    def test_setting_key_exists_with_safe_default(self):
        self.assertIn("startup", main.DEFAULT_SETTINGS)
        self.assertFalse(main.DEFAULT_SETTINGS["startup"])


# ── 한글 조합(IME preedit) 중 치환: 앞 띄어쓰기 보존 ────────────────
class TestComposingTailDetection(unittest.TestCase):
    """한글 모드로 단축어를 치면 마지막 글자가 IME '조합 중'(preedit) 상태다.
    조합 중인 글자는 아직 문서에 들어가 있지 않아서, 백스페이스를 그냥 보내면
    앱에 따라 그 글자가 백스페이스를 소비하지 않고 사라진다 → 보낸 백스페이스가
    전부 확정된 앞 글자에 꽂혀 **단축어 앞의 띄어쓰기까지 지워진다**
    ("안녕. ;;cl" 을 한글 모드로 치면 "안녕.결과").

    그래서 주입 직전에 조합을 확정시켜야 하고, 그러려면 '지금 조합 중인지'를
    치환 계산 단계에서 알려 줘야 한다."""

    def test_is_jamo(self):
        for ch in ("ㅊ", "ㅣ", "ㅏ", "ㄴ"):
            self.assertTrue(main.is_jamo(ch), ch)
        for ch in ("치", "a", ";", " ", "1", "", "가"):
            self.assertFalse(main.is_jamo(ch), repr(ch))

    def _sim(self, trigger, output=";;OUT"):
        return _ScreenSim({"type": "special", "trigger": trigger,
                           "output": output, "enabled": True}, normalize=True)

    def _type_raw(self, sim, chars):
        for ch in chars:
            sim.raw += ch
            sim.L._on_press(_FakeCharKey(ch))
        return sim

    def test_korean_mode_trigger_is_flagged_composing(self):
        # 한글 모드로 ";;cl" → 실제로는 ';', ';', 'ㅊ', 'ㅣ' 가 들어온다.
        s = self._sim(";;cl", "결과")
        s.type_jamo("안녕. ")
        self._type_raw(s, ";;ㅊㅣ")
        self.assertTrue(s.cap.get("composing"),
                        "마지막 글자가 자모면 조합 중으로 보고해야 한다")
        self.assertEqual(s.cap.get("bs"), 3, '화면상 ";;치" 3글자')
        self.assertEqual(s.screen_after(), "안녕. 결과",
                         "앞의 띄어쓰기가 남아야 한다")

    def test_english_mode_trigger_is_not_composing(self):
        s = self._sim(";;cl", "결과")
        s.type_jamo("안녕. ")
        self._type_raw(s, ";;cl")
        self.assertFalse(s.cap.get("composing"),
                         "영문 입력은 조합이 없다 → 확정 절차 불필요")
        self.assertEqual(s.screen_after(), "안녕. 결과")

    def test_completed_syllable_trigger_is_not_composing(self):
        # 트리거가 완성형으로 끝나면(예: 뒤에 확정을 부른 입력이 있었던 경우)
        # 조합 중이 아니다.
        s = self._sim(";;가", "결과")
        s.type_jamo("안녕. ")
        self._type_raw(s, ";;")
        s.raw += "가"
        s.L._on_press(_FakeCharKey("가"))
        self.assertFalse(s.cap.get("composing"))


class TestImeCommitBeforeBackspace(unittest.TestCase):
    """주입 스레드는 백스페이스보다 **먼저** 조합을 확정시켜야 한다.
    확정 수단은 두 가지: (1) IME 변환모드를 영문으로(메시지 방식),
    (2) 그 메시지를 무시하는 앱을 위해 진짜 한/영 키. 끝나면 원복한다."""

    def setUp(self):
        self.order = []
        self._force = main.ime_force_alphanumeric
        self._restore = main.ime_restore
        self._toggle = main.send_hangul_toggle
        self._send = main.send_text
        main.send_text = lambda *a, **k: (self.order.append("type"), True)[1]
        main.ime_restore = lambda saved: self.order.append("restore")
        main.send_hangul_toggle = lambda: (self.order.append("toggle"), True)[1]

    def tearDown(self):
        main.ime_force_alphanumeric = self._force
        main.ime_restore = self._restore
        main.send_hangul_toggle = self._toggle
        main.send_text = self._send

    def _listener(self):
        L = main.KeyboardListener()
        L.controller = _RecordingController(self.order)
        return L

    def test_mode_switch_commits_before_backspaces(self):
        main.ime_force_alphanumeric = lambda: (self.order.append("force"),
                                               ("ime", 1))[1]
        L = self._listener()
        L._inject_replacement("t", "OUT", "OUT", 2, composing=True)
        self.assertLess(self.order.index("force"), self.order.index("bs"),
                        "조합 확정이 백스페이스보다 먼저여야 한다")
        self.assertIn("restore", self.order)
        self.assertNotIn("toggle", self.order,
                         "메시지 방식이 통했으면 한/영 키는 누르지 않는다")

    def test_hangul_key_fallback_when_mode_switch_fails(self):
        main.ime_force_alphanumeric = lambda: None  # Chromium 등: 메시지 무시
        L = self._listener()
        L._inject_replacement("t", "OUT", "OUT", 2, composing=True)
        self.assertEqual(self.order.count("toggle"), 2,
                         "확정용 한 번 + 원복용 한 번")
        self.assertLess(self.order.index("toggle"), self.order.index("bs"))

    def test_no_toggle_when_not_composing(self):
        main.ime_force_alphanumeric = lambda: None
        L = self._listener()
        L._inject_replacement("t", "OUT", "OUT", 2, composing=False)
        self.assertNotIn("toggle", self.order,
                         "조합이 없으면 한/영 키를 건드리지 않는다")


class _RecordingController:
    """pynput Controller 대역 — 백스페이스 순서만 기록한다."""

    def __init__(self, order):
        self.order = order

    def press(self, key):
        if key == main.Key.backspace and "bs" not in self.order:
            self.order.append("bs")

    def release(self, key):
        pass

    def type(self, text):
        self.order.append("type")


if __name__ == "__main__":
    unittest.main(verbosity=2)

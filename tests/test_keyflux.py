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
        # 잘못된(존재하지 않는) 형식은 원본을 보존
        self.assertEqual(main.resolve_output("{nope}"), "{nope}")


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
                      visible_chars=None):
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
        # 레지스트리를 변경하지 않고 조회만 — 항상 bool 반환
        self.assertIsInstance(main.is_startup_enabled(), bool)

    def test_startup_target_command_nonempty(self):
        if sys.platform == "win32":
            self.assertTrue(main._startup_target_command())


if __name__ == "__main__":
    unittest.main(verbosity=2)

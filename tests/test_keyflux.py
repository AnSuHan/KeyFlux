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
import unittest

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


if __name__ == "__main__":
    unittest.main(verbosity=2)

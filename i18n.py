"""KeyFlux 다국어 문구.

원문(한국어)을 키로 쓴다: tr("그룹 '{name}' 추가됨", name=...).
{이름} 자리는 넘긴 인자만 바뀐다. 출력 문법인 {date}, {1} 등은 그대로 남는다.
문구를 추가하면 _T 에 (English, 日本語, 简体中文) 순으로 번역을 함께 넣는다
(빠지면 tests 의 TestI18n 이 실패한다).
"""
import re

LANGUAGES = {"ko": "한국어", "en": "English", "ja": "日本語", "zh": "简体中文"}
_COLUMN = {"en": 0, "ja": 1, "zh": 2}
_lang = "ko"


def resolve_language(setting, system_languages=()) -> str:
    """설정값("auto" 또는 언어 코드)을 실제로 쓸 언어 코드로 바꾼다."""
    if setting in LANGUAGES:
        return setting
    first = next(iter(system_languages), "")
    code = first.replace("_", "-").split("-")[0].lower()
    return code if code in LANGUAGES else "en"


def set_language(code: str):
    global _lang
    _lang = code if code in LANGUAGES else "en"


def language() -> str:
    return _lang


def translations(text: str) -> set:
    """한 문구의 모든 언어 표기(원문 포함)."""
    return {text, *_T.get(text, ())}


def tr(text: str, /, **values) -> str:
    if _lang in _COLUMN and text in _T:
        text = _T[text][_COLUMN[_lang]]
    if not values:
        return text
    return re.sub(r"\{(\w+)\}",
                  lambda m: str(values[m[1]]) if m[1] in values else m[0], text)


_T = {
    # ── 공통 ──
    "편집": ("Edit", "編集", "编辑"),
    "삭제": ("Delete", "削除", "删除"),
    "저장": ("Save", "保存", "保存"),
    "취소": ("Cancel", "キャンセル", "取消"),
    "이름": ("Name", "名前", "名称"),
    "값": ("Value", "値", "值"),
    "알림": ("Notice", "お知らせ", "提示"),
    "완료": ("Done", "完了", "完成"),
    "오류": ("Error", "エラー", "错误"),
    "삭제 확인": ("Confirm deletion", "削除の確認", "确认删除"),
    "전체": ("All", "すべて", "全部"),
    "미분류": ("Ungrouped", "未分類", "未分组"),
    "(미분류)": ("(Ungrouped)", "(未分類)", "(未分组)"),

    # ── 메인 창 · 트레이 ──
    " (관리자)": (" (Administrator)", " (管理者)", " (管理员)"),
    "키 입력 자동 변환 · 백그라운드 실행": (
        "Automatic text expansion · runs in the background",
        "キー入力の自動変換 · バックグラウンド実行",
        "按键自动替换 · 后台运行"),
    "● 활성화됨": ("● Active", "● 有効", "● 已启用"),
    "○ 비활성화됨": ("○ Paused", "○ 無効", "○ 已停用"),
    "+ 규칙 추가": ("+ Add rule", "+ ルール追加", "+ 添加规则"),
    "↑ 내보내기": ("↑ Export", "↑ エクスポート", "↑ 导出"),
    "↓ 불러오기": ("↓ Import", "↓ インポート", "↓ 导入"),
    "현재 규칙을 JSON 파일로 저장합니다": (
        "Save the current rules to a JSON file",
        "現在のルールをJSONファイルに保存します",
        "将当前规则保存为 JSON 文件"),
    "JSON 파일에서 규칙을 불러옵니다": (
        "Load rules from a JSON file",
        "JSONファイルからルールを読み込みます",
        "从 JSON 文件导入规则"),
    "⚙ 설정": ("⚙ Settings", "⚙ 設定", "⚙ 设置"),
    "동작 옵션을 설정 창에서 조작합니다": (
        "Change language and behavior options",
        "言語と動作オプションを変更します",
        "更改语言和行为选项"),
    "활성": ("On", "有効", "启用"),
    "타입": ("Type", "種類", "类型"),
    "그룹": ("Group", "グループ", "分组"),
    "트리거": ("Trigger", "トリガー", "触发词"),
    "출력": ("Output", "出力", "输出"),
    "대기 중...": ("Waiting...", "待機中...", "等待中..."),
    "변환 중지됨": ("Expansion paused", "変換を停止しました", "已暂停替换"),
    "설정 파일: {path}": ("Config file: {path}", "設定ファイル: {path}", "配置文件: {path}"),
    "변환됨: {msg}": ("Expanded: {msg}", "変換しました: {msg}", "已替换: {msg}"),
    "열기": ("Open", "開く", "打开"),
    "활성화 토글": ("Pause / resume", "有効/無効の切り替え", "启用/停用"),
    "종료": ("Quit", "終了", "退出"),
    "KeyFlux v{version} - 실행 중": (
        "KeyFlux v{version} - running", "KeyFlux v{version} - 実行中", "KeyFlux v{version} - 运行中"),
    "트레이에서 계속 실행 중입니다.": (
        "Still running in the system tray.",
        "トレイで実行を続けています。",
        "仍在系统托盘中运行。"),
    "프로그램이 이미 실행 중입니다.\n트레이 아이콘을 확인하세요.": (
        "KeyFlux is already running.\nCheck the tray icon.",
        "KeyFlux はすでに実行中です。\nトレイアイコンを確認してください。",
        "KeyFlux 已在运行。\n请查看托盘图标。"),
    "\nKeyFlux 종료됨 (Ctrl+C)": (
        "\nKeyFlux stopped (Ctrl+C)", "\nKeyFlux を終了しました (Ctrl+C)", "\nKeyFlux 已退出 (Ctrl+C)"),

    # ── 버전 · 패치 내역 ──
    "v{version} · 패치 내역": (
        "v{version} · Patch notes", "v{version} · 更新履歴", "v{version} · 更新日志"),
    "KeyFlux 패치 내역": ("KeyFlux patch notes", "KeyFlux 更新履歴", "KeyFlux 更新日志"),
    "현재 버전: v{version}": (
        "Current version: v{version}", "現在のバージョン: v{version}", "当前版本: v{version}"),
    "버전별 변경 사항을 봅니다": (
        "See what changed in each version",
        "バージョンごとの変更点を表示します",
        "查看各版本的更改内容"),
    "패치 내역": ("Patch notes", "更新履歴", "更新日志"),

    # ── 규칙 편집 ──
    "규칙 추가": ("Add rule", "ルール追加", "添加规则"),
    "규칙 편집": ("Edit rule", "ルール編集", "编辑规则"),
    "special (;단축어)": ("special (;shortcut)", "special (;ショートカット)", "special (;快捷词)"),
    "word (단어)": ("word (whole word)", "word (単語)", "word (单词)"),
    "regex (정규식)": ("regex (regular expression)", "regex (正規表現)", "regex (正则表达式)"),
    "예: abc  또는  ;date  또는  \\d{4}": (
        "e.g. abc  or  ;date  or  \\d{4}",
        "例: abc  または  ;date  または  \\d{4}",
        "例如: abc  或  ;date  或  \\d{4}"),
    "예: 123  또는  {date}  또는  [DATE]\n(Ctrl+Enter 로 저장)": (
        "e.g. 123  or  {date}  or  [DATE]\n(Ctrl+Enter to save)",
        "例: 123  または  {date}  または  [DATE]\n(Ctrl+Enter で保存)",
        "例如: 123  或  {date}  或  [DATE]\n(Ctrl+Enter 保存)"),
    "키워드를 묶을 그룹. 목록에서 고르거나 새 이름을 입력하면 그룹이 만들어집니다. 그룹 단위로 켜고 끌 수 있습니다.": (
        "Group for this keyword. Pick one or type a new name to create it. Groups can be switched on and off as a whole.",
        "キーワードのグループ。一覧から選ぶか、新しい名前を入力すると作成されます。グループ単位でオン/オフできます。",
        "关键词所属分组。可从列表选择，或输入新名称创建。可按分组整体启用或停用。"),
    "줄바꿈 키": ("Line break", "改行キー", "换行键"),
    "Shift+Enter (기본)": ("Shift+Enter (default)", "Shift+Enter (既定)", "Shift+Enter (默认)"),
    "Enter (전송·실행)": ("Enter (send / run)", "Enter (送信・実行)", "Enter (发送/执行)"),
    "출력 칸에서 Enter 를 누를 때 넣을 키입니다. Enter 로 저장한 줄바꿈은 {enter} 로 표시됩니다.": (
        "The key that pressing Enter in the output box records. Breaks saved as Enter are shown as {enter}.",
        "出力欄で Enter を押したときに記録するキーです。Enter として保存した改行は {enter} と表示されます。",
        "在输出框中按 Enter 时记录的按键。保存为 Enter 的换行显示为 {enter}。"),
    "미리보기": ("Preview", "プレビュー", "预览"),
    "{date} {time} {datetime} · {1} {2} {*}(인자) · {이름}(변수)\n형식 지정: {date:%Y%m%d} → 20260711   {time:%H:%M} → 20:03\n줄바꿈 = Shift+Enter · {enter} = Enter\n자세한 문법은 아래 '문법 도움말' 참고 · Ctrl+Enter 로 저장": (
        "{date} {time} {datetime} · {1} {2} {*} (args) · {name} (variable)\nFormat: {date:%Y%m%d} → 20260711   {time:%H:%M} → 20:03\nLine break = Shift+Enter · {enter} = Enter\nSee 'Syntax help' below · Ctrl+Enter to save",
        "{date} {time} {datetime} · {1} {2} {*}(引数) · {名前}(変数)\n書式: {date:%Y%m%d} → 20260711   {time:%H:%M} → 20:03\n改行 = Shift+Enter · {enter} = Enter\n詳しくは下の「文法ヘルプ」 · Ctrl+Enter で保存",
        "{date} {time} {datetime} · {1} {2} {*}(参数) · {名称}(变量)\n格式: {date:%Y%m%d} → 20260711   {time:%H:%M} → 20:03\n换行 = Shift+Enter · {enter} = Enter\n详见下方“语法帮助” · Ctrl+Enter 保存"),
    "? 문법 도움말": ("? Syntax help", "? 文法ヘルプ", "? 语法帮助"),
    "출력에 쓸 수 있는 모든 문법을 봅니다": (
        "See all syntax available in outputs",
        "出力で使えるすべての文法を表示します",
        "查看输出中可用的所有语法"),
    "인자{n}": ("arg{n}", "引数{n}", "参数{n}"),
    "이 규칙은 호출 시 인자를 받습니다 — 트리거 뒤에 공백으로 인자를 입력하고 Enter 로 확정하세요. (아래는 샘플 인자 예시)": (
        "This rule takes arguments: type them after the trigger, separated by spaces, then press Enter. (Sample arguments shown below)",
        "このルールは引数を受け取ります。トリガーの後に空白区切りで入力し、Enter で確定します。(下はサンプル引数の例)",
        "此规则接受参数：在触发词后用空格分隔输入参数，按 Enter 确认。(下方为示例参数)"),
    "(출력 내용을 입력하세요)": ("(Enter the output)", "(出力内容を入力してください)", "(请输入输出内容)"),
    "형식 오류: {error}": ("Format error: {error}", "書式エラー: {error}", "格式错误: {error}"),

    # ── 변수 ──
    "변수 추가": ("Add variable", "変数追加", "添加变量"),
    "변수 편집": ("Edit variable", "変数編集", "编辑变量"),
    "+ 변수 추가": ("+ Add variable", "+ 変数追加", "+ 添加变量"),
    "예: 회사  (출력에서 {회사} 로 사용)": (
        "e.g. company  (use as {company})", "例: 会社  (出力で {会社} として使用)", "例如: 公司  (在输出中用 {公司})"),
    "예: 한빛": ("e.g. Acme", "例: 山田商事", "例如: 星光科技"),
    "이름에 { } : 기호·순수 숫자·* 는 쓸 수 없습니다.": (
        "Names cannot contain { } : or be only digits or *.",
        "名前に { } : 、数字のみ、* は使えません。",
        "名称不能包含 { } : ，也不能是纯数字或 *。"),
    "변수명 오류": ("Invalid name", "変数名エラー", "变量名错误"),
    "중복": ("Duplicate", "重複", "重复"),
    "'{name}' 변수가 이미 있습니다.": (
        "Variable '{name}' already exists.", "変数「{name}」はすでにあります。", "变量“{name}”已存在。"),
    "변수명을 입력하세요.": ("Enter a variable name.", "変数名を入力してください。", "请输入变量名。"),
    "변수명에 { } : 기호는 쓸 수 없습니다.": (
        "Variable names cannot contain { } :", "変数名に { } : は使えません。", "变量名不能包含 { } :"),
    "숫자만으로 된 변수명은 위치 인자({1},{2}…)와 충돌합니다.": (
        "A digits-only name conflicts with positional arguments ({1},{2}…).",
        "数字のみの変数名は位置引数({1},{2}…)と衝突します。",
        "纯数字变量名会与位置参数({1},{2}…)冲突。"),
    "'*' 는 전체 인자({*})에 예약되어 있습니다.": (
        "'*' is reserved for all arguments ({*}).",
        "「*」は全引数({*})用に予約されています。",
        "“*”保留给全部参数({*})。"),
    "'{name}' 은(는) 예약어입니다.": (
        "'{name}' is a reserved word.", "「{name}」は予約語です。", "“{name}”是保留字。"),
    "변수 관리  (출력에서 {이름} 으로 재사용)": (
        "Variables  (reuse as {name} in outputs)", "変数管理  (出力で {名前} として再利用)", "变量管理  (在输出中用 {名称} 复用)"),
    "편집할 변수를 선택하세요.": ("Select a variable to edit.", "編集する変数を選択してください。", "请选择要编辑的变量。"),
    "삭제할 변수를 선택하세요.": ("Select a variable to delete.", "削除する変数を選択してください。", "请选择要删除的变量。"),
    "'{name}' 변수를 삭제할까요?": ("Delete variable '{name}'?", "変数「{name}」を削除しますか?", "删除变量“{name}”？"),
    "변수 {n}개 저장됨": ("Variables saved: {n}", "変数を{n}件保存しました", "已保存 {n} 个变量"),

    # ── 설정 ──
    "KeyFlux 설정 (v{version})": (
        "KeyFlux settings (v{version})", "KeyFlux 設定 (v{version})", "KeyFlux 设置 (v{version})"),
    "언어": ("Language", "言語", "语言"),
    "시스템 언어": ("System language", "システムの言語", "系统语言"),
    "매칭 동작": ("Matching", "マッチング", "匹配"),
    "알림 · 시작": ("Notifications · Startup", "通知 · 起動", "通知 · 启动"),
    "진단": ("Diagnostics", "診断", "诊断"),
    "한/영·대소문자 무관 매칭": (
        "Match regardless of Korean/English mode and case",
        "韓/英・大文字小文字を区別しない",
        "匹配时忽略韩/英模式和大小写"),
    "켜면 한/영 입력 상태나 대소문자와 상관없이 트리거가 동작합니다.\n(예: 영문 모드든 한글 모드든 같은 키를 누르면 변환)": (
        "Triggers work in either Korean or English mode and in any case.\n(The same physical keys expand in both modes)",
        "韓/英の入力状態や大文字小文字に関係なくトリガーが動作します。\n(どちらのモードでも同じキーで変換)",
        "无论韩/英输入状态或大小写，触发词均生效。\n(两种模式下按相同按键都会替换)"),
    "결과 대소문자 보장": ("Keep saved case in output", "出力の大文字小文字を保持", "保持输出大小写"),
    "켜면 CapsLock 이 켜져 있어도 출력 결과의 대소문자가\n저장한 그대로 들어갑니다. 끄면 CapsLock 상태에 따라\n대소문자가 뒤집힐 수 있습니다.": (
        "Output keeps the saved case even with CapsLock on.\nWhen off, CapsLock may invert the case.",
        "CapsLock がオンでも保存したとおりに出力します。\nオフにすると CapsLock により反転することがあります。",
        "即使开启 CapsLock，也按保存的大小写输出。\n关闭时，CapsLock 可能使大小写反转。"),
    "알림 표시": ("Show notifications", "通知を表示", "显示通知"),
    "켜면 변환 결과와 트레이 안내를 윈도우 알림(풍선)으로 표시합니다.": (
        "Show expansion results and tray messages as Windows notifications.",
        "変換結果とトレイの案内を Windows 通知で表示します。",
        "以 Windows 通知显示替换结果和托盘提示。"),
    "시작 시 자동 실행": ("Run at startup", "起動時に自動実行", "开机自动运行"),
    "켜면 Windows 로그인 시 KeyFlux 가 자동으로 실행됩니다. 작업 스케줄러에 등록되며(관리자 권한·UAC 창 없음), 배터리로 켜도 실행됩니다. 등록이 사라지면 다음 실행 때 자동으로 복구합니다.": (
        "Start KeyFlux when you sign in to Windows. It is registered in Task Scheduler (elevated, no UAC prompt), also runs on battery, and repairs itself on the next launch if the task is lost.",
        "Windows へのサインイン時に KeyFlux を自動実行します。タスクスケジューラに登録され(管理者権限・UAC なし)、バッテリー駆動でも動作します。登録が消えても次回起動時に復旧します。",
        "登录 Windows 时自动运行 KeyFlux。通过任务计划程序注册(管理员权限、无 UAC 弹窗)，使用电池时也会运行。若注册丢失，下次启动时自动修复。"),
    "디버그 로그": ("Debug log", "デバッグログ", "调试日志"),
    "켜면 키 감지·치환·주입 과정을 파일로 기록합니다.\n기록 위치: {path}": (
        "Log key detection, replacement and injection to a file.\nLocation: {path}",
        "キー検出・置換・入力の過程をファイルに記録します。\n保存先: {path}",
        "将按键检测、替换和输入过程记录到文件。\n位置: {path}"),
    "한/영·대소문자 무관 매칭 켜짐": (
        "Mode- and case-insensitive matching on", "韓/英・大文字小文字の区別なし: オン", "忽略韩/英和大小写: 开"),
    "한/영·대소문자 무관 매칭 꺼짐": (
        "Mode- and case-insensitive matching off", "韓/英・大文字小文字の区別なし: オフ", "忽略韩/英和大小写: 关"),
    "결과 대소문자 보장 켜짐": ("Keep saved case: on", "大文字小文字の保持: オン", "保持输出大小写: 开"),
    "결과 대소문자 보장 꺼짐": ("Keep saved case: off", "大文字小文字の保持: オフ", "保持输出大小写: 关"),
    "윈도우 알림 켜짐": ("Notifications on", "通知: オン", "通知: 开"),
    "윈도우 알림 꺼짐": ("Notifications off", "通知: オフ", "通知: 关"),
    "디버그 로그 기록: {path}": ("Writing debug log: {path}", "デバッグログを記録中: {path}", "正在记录调试日志: {path}"),
    "디버그 로그 꺼짐": ("Debug log off", "デバッグログ: オフ", "调试日志: 关"),
    "시작 시 자동 실행 등록됨": ("Run at startup: registered", "自動実行を登録しました", "已注册开机自动运行"),
    "시작 시 자동 실행 해제됨": ("Run at startup: removed", "自動実行を解除しました", "已取消开机自动运行"),
    " (제한 모드: 작업 스케줄러 등록 실패 → 레지스트리 등록)": (
        " (limited mode: Task Scheduler failed → using the registry)",
        " (制限モード: タスク登録に失敗 → レジストリに登録)",
        " (受限模式: 任务计划注册失败 → 已写入注册表)"),
    "시작 프로그램 설정에 실패했습니다.": (
        "Could not change the startup setting.", "自動実行の設定に失敗しました。", "开机启动设置失败。"),
    "Windows 에서만 지원합니다.": ("Supported on Windows only.", "Windows のみ対応しています。", "仅支持 Windows。"),
    "KeyFlux - 키 입력 자동 변환기 (로그인 시 자동 실행)": (
        "KeyFlux - text expander (runs at sign-in)",
        "KeyFlux - キー入力自動変換 (サインイン時に実行)",
        "KeyFlux - 按键自动替换 (登录时运行)"),

    # ── 그룹 ──
    "키워드 그룹": ("Keyword groups", "キーワードグループ", "关键词分组"),
    "클릭: 해당 그룹의 키워드만 보기\n체크 해제: 그 그룹의 키워드를 모두 끄기(목록에는 남음)\n더블클릭/우클릭: 이름 변경·삭제": (
        "Click: show only this group\nUncheck: turn off all its keywords (they stay listed)\nDouble/right-click: rename or delete",
        "クリック: このグループのみ表示\nチェック解除: グループ内をすべてオフ(一覧には残る)\nダブル/右クリック: 名前変更・削除",
        "单击: 仅显示该分组\n取消勾选: 停用该分组全部关键词(仍保留在列表)\n双击/右键: 重命名或删除"),
    "+ 그룹": ("+ Group", "+ 追加", "+ 分组"),
    "이름 바꾸기": ("Rename", "改名", "改名"),
    "새 키워드 그룹을 만듭니다": ("Create a keyword group", "新しいグループを作成します", "新建关键词分组"),
    "선택한 그룹 이름 변경": ("Rename the selected group", "選択したグループの名前を変更", "重命名所选分组"),
    "선택한 그룹 삭제(키워드는 미분류로 이동)": (
        "Delete the selected group (keywords become ungrouped)",
        "選択したグループを削除(キーワードは未分類へ移動)",
        "删除所选分组(关键词移至未分组)"),
    "꺼짐 — 이 그룹의 키워드는 동작하지 않습니다": (
        "Off: keywords in this group do not expand",
        "オフ: このグループのキーワードは動作しません",
        "已停用: 该分组的关键词不生效"),
    "그룹 '{name}' 켜짐": ("Group '{name}' on", "グループ「{name}」: オン", "分组“{name}”: 开"),
    "그룹 '{name}' 꺼짐 (키워드 동작 안 함)": (
        "Group '{name}' off (keywords inactive)",
        "グループ「{name}」: オフ (キーワードは動作しません)",
        "分组“{name}”: 关 (关键词不生效)"),
    "+ 새 그룹": ("+ New group", "+ 新規グループ", "+ 新建分组"),
    "새 그룹…": ("New group…", "新規グループ…", "新建分组…"),
    "이름 변경": ("Rename", "名前の変更", "重命名"),
    "그룹 이름:": ("Group name:", "グループ名:", "分组名称:"),
    "그룹 이름": ("Group name", "グループ名", "分组名称"),
    "그룹 추가": ("Add group", "グループ追加", "添加分组"),
    "그룹 이름 변경": ("Rename group", "グループ名の変更", "重命名分组"),
    "그룹 삭제": ("Delete group", "グループ削除", "删除分组"),
    "그룹 이동": ("Move to group", "グループへ移動", "移动到分组"),
    "그룹 이름을 입력하세요.": ("Enter a group name.", "グループ名を入力してください。", "请输入分组名称。"),
    "'{name}' 은(는) 그룹 이름으로 쓸 수 없습니다.": (
        "'{name}' cannot be used as a group name.",
        "「{name}」はグループ名に使えません。",
        "“{name}”不能用作分组名称。"),
    "'{name}' 그룹이 이미 있습니다.": (
        "Group '{name}' already exists.", "グループ「{name}」はすでにあります。", "分组“{name}”已存在。"),
    "그룹 '{name}' 추가됨": ("Group '{name}' added", "グループ「{name}」を追加しました", "已添加分组“{name}”"),
    "이름을 바꿀 그룹을 선택하세요.": ("Select a group to rename.", "名前を変更するグループを選択してください。", "请选择要重命名的分组。"),
    "그룹 이름 변경: '{old}' → '{new}'": (
        "Group renamed: '{old}' → '{new}'", "グループ名を変更: 「{old}」→「{new}」", "分组已重命名: “{old}”→“{new}”"),
    "삭제할 그룹을 선택하세요.": ("Select a group to delete.", "削除するグループを選択してください。", "请选择要删除的分组。"),
    "'{name}' 그룹을 삭제할까요?": ("Delete group '{name}'?", "グループ「{name}」を削除しますか?", "删除分组“{name}”？"),
    "\n\n이 그룹의 키워드 {n}개는 삭제되지 않고 '{label}'로 이동합니다.": (
        "\n\nKeywords in this group ({n}) are kept and moved to '{label}'.",
        "\n\nこのグループのキーワード{n}件は削除されず「{label}」へ移動します。",
        "\n\n该分组的 {n} 个关键词不会被删除，将移至“{label}”。"),
    "그룹 '{name}' 삭제됨": ("Group '{name}' deleted", "グループ「{name}」を削除しました", "已删除分组“{name}”"),
    "\"{trigger}\" → 그룹 '{name}'": (
        "\"{trigger}\" → group '{name}'", "「{trigger}」→ グループ「{name}」", "“{trigger}”→ 分组“{name}”"),
    "그룹 '{name}' 이(가) 꺼져 있어 동작하지 않습니다": (
        "Inactive because group '{name}' is off",
        "グループ「{name}」がオフのため動作しません",
        "分组“{name}”已停用，因此不生效"),

    # ── 규칙 CRUD · 가져오기/내보내기 ──
    "편집할 규칙을 선택하세요.": ("Select a rule to edit.", "編集するルールを選択してください。", "请选择要编辑的规则。"),
    "삭제할 규칙을 선택하세요.": ("Select a rule to delete.", "削除するルールを選択してください。", "请选择要删除的规则。"),
    "\"{trigger}\" 규칙을 삭제할까요?": (
        "Delete rule \"{trigger}\"?", "ルール「{trigger}」を削除しますか?", "删除规则“{trigger}”？"),
    "규칙 내보내기": ("Export rules", "ルールのエクスポート", "导出规则"),
    "규칙 불러오기": ("Import rules", "ルールのインポート", "导入规则"),
    "JSON 파일 (*.json)": ("JSON files (*.json)", "JSON ファイル (*.json)", "JSON 文件 (*.json)"),
    "규칙을 저장했습니다.\n{path}": ("Rules saved.\n{path}", "ルールを保存しました。\n{path}", "规则已保存。\n{path}"),
    "저장 실패: {error}": ("Save failed: {error}", "保存に失敗しました: {error}", "保存失败: {error}"),
    "규칙 목록이 배열 형식이 아닙니다.": ("The rule list is not an array.", "ルール一覧が配列ではありません。", "规则列表不是数组格式。"),
    "잘못된 규칙 항목: {rule}": ("Invalid rule: {rule}", "不正なルール: {rule}", "无效的规则: {rule}"),
    "불러오기 방식": ("Import mode", "インポート方法", "导入方式"),
    "기존 규칙을 대체할까요?\n\n[예] 대체   [아니요] 기존에 추가": (
        "Replace the existing rules?\n\n[Yes] Replace   [No] Add to existing",
        "既存のルールを置き換えますか?\n\n[はい] 置換   [いいえ] 追加",
        "替换现有规则？\n\n[是] 替换   [否] 追加"),
    "{n}개 규칙을 불러왔습니다 (대체).": (
        "Rules imported: {n} (replaced).", "{n}件のルールを読み込みました (置換)。", "已导入 {n} 条规则 (替换)。"),
    "{n}개 규칙을 추가했습니다.": ("Rules added: {n}.", "{n}件のルールを追加しました。", "已添加 {n} 条规则。"),
    "불러오기 실패: {error}": ("Import failed: {error}", "読み込みに失敗しました: {error}", "导入失败: {error}"),

    # ── 문법 도움말 ──
    "출력 문법 도움말": ("Output syntax help", "出力文法ヘルプ", "输出语法帮助"),
    "현재 등록된 변수 (설정 → 변수 관리에서 추가/수정):": (
        "Current variables (edit in Settings → Variables):",
        "登録済みの変数 (設定 → 変数管理で編集):",
        "当前变量 (在设置 → 变量管理中编辑):"),
    "아직 등록된 변수가 없습니다. <b>설정 → 변수 관리</b>에서 <code>{회사}=한빛</code> 처럼 추가하면 출력에서 <code>{회사}</code> 로 재사용할 수 있습니다.": (
        "No variables yet. Add one such as <code>{company}=Acme</code> in <b>Settings → Variables</b> and reuse it as <code>{company}</code>.",
        "変数はまだありません。<b>設定 → 変数管理</b>で <code>{会社}=山田商事</code> のように追加すると <code>{会社}</code> として再利用できます。",
        "还没有变量。在<b>设置 → 变量管理</b>中添加如 <code>{公司}=星光科技</code>，即可用 <code>{公司}</code> 复用。"),
    "1. 날짜 · 시간": ("1. Date · time", "1. 日付 · 時刻", "1. 日期 · 时间"),
    "오늘 날짜": ("Today's date", "今日の日付", "今天日期"),
    "현재 시각": ("Current time", "現在時刻", "当前时间"),
    "날짜+시각": ("Date and time", "日付+時刻", "日期+时间"),
    "형식 지정": ("Custom format", "書式指定", "指定格式"),
    "2. 호출 시 인자 (위치 인자)": (
        "2. Arguments (positional)", "2. 呼び出し時の引数 (位置引数)", "2. 调用参数 (位置参数)"),
    "<b>special(;단축어) 규칙</b>의 출력에 <code>{1}</code> <code>{2}</code> … 를 넣으면, 트리거를 친 뒤 <b>공백으로 인자를 이어 입력하고 Enter 로 확정</b>합니다.": (
        "With <code>{1}</code> <code>{2}</code> … in a <b>special (;shortcut) rule</b>, type the trigger, then <b>the arguments separated by spaces, then Enter</b>.",
        "<b>special(;ショートカット)ルール</b>の出力に <code>{1}</code> <code>{2}</code> … を入れると、トリガーの後に<b>空白区切りで引数を入力し Enter で確定</b>します。",
        "在 <b>special(;快捷词)规则</b>的输出中使用 <code>{1}</code> <code>{2}</code> … 时，输入触发词后<b>用空格分隔输入参数，按 Enter 确认</b>。"),
    "공백으로 구분한 1·2번째 인자": (
        "1st and 2nd space-separated argument", "空白区切りの1・2番目の引数", "以空格分隔的第 1、2 个参数"),
    "인자 전체(내부 공백 보존)": (
        "All arguments (spaces preserved)", "引数全体(空白を保持)", "全部参数(保留空格)"),
    "{1:기본값}": ("{1:default}", "{1:既定値}", "{1:默认值}"),
    "그 인자가 없을 때 쓸 기본값": (
        "Default when the argument is missing", "引数がない場合の既定値", "缺少该参数时的默认值"),
    "예) 트리거 <code>;메일</code>, 출력 <code>{1} 님께</code> → <span class=\"ex\">;메일 홍길동⏎</span> 입력 시 <span class=\"ex\">홍길동 님께</span>": (
        "Example: trigger <code>;mail</code>, output <code>Dear {1}</code> → typing <span class=\"ex\">;mail Alex⏎</span> gives <span class=\"ex\">Dear Alex</span>",
        "例) トリガー <code>;mail</code>、出力 <code>{1} 様</code> → <span class=\"ex\">;mail 山田⏎</span> で <span class=\"ex\">山田 様</span>",
        "例) 触发词 <code>;mail</code>，输出 <code>{1} 您好</code> → 输入 <span class=\"ex\">;mail 小王⏎</span> 得到 <span class=\"ex\">小王 您好</span>"),
    "3. 재사용 변수": ("3. Variables", "3. 再利用変数", "3. 可复用变量"),
    "{이름}": ("{name}", "{名前}", "{名称}"),
    "미리 정의한 값으로 치환": ("Replaced by the saved value", "定義済みの値に置換", "替换为预定义的值"),
    "4. 줄바꿈": ("4. Line breaks", "4. 改行", "4. 换行"),
    "일반 줄바꿈": ("Plain line break", "通常の改行", "普通换行"),
    "Shift+Enter 로 입력 (기본 — 메신저에서 전송되지 않음)": (
        "Typed as Shift+Enter (default; does not send in messengers)",
        "Shift+Enter で入力 (既定。メッセンジャーで送信されない)",
        "按 Shift+Enter 输入 (默认，在聊天软件中不会发送)"),
    "Enter 로 입력 (전송·실행). 바로 뒤 줄바꿈 1개는 같은 Enter 로 처리": (
        "Typed as Enter (send / run). One line break right after it belongs to the same Enter",
        "Enter で入力 (送信・実行)。直後の改行1つは同じ Enter として扱う",
        "按 Enter 输入 (发送/执行)。紧随其后的一个换行视为同一次 Enter"),
    "5. 리터럴 중괄호": ("5. Literal braces", "5. 波括弧そのもの", "5. 字面花括号"),
    "중괄호 자체를 그대로 출력하고 싶을 때": (
        "To output the braces themselves", "波括弧自体を出力したいとき", "需要输出花括号本身时"),
    "참고": ("Notes", "補足", "说明"),
    "인자 입력(위 2번)은 <b>special 트리거</b>에서만 동작합니다(word/regex 제외).": (
        "Arguments (section 2) work with <b>special triggers</b> only (not word/regex).",
        "引数入力(上の2)は <b>special トリガー</b>のみで動作します(word/regex は対象外)。",
        "参数输入(第 2 节)仅适用于 <b>special 触发词</b>(不含 word/regex)。"),
    "인자에는 한글도 그대로 쓸 수 있습니다(화면에 보이는 그대로 삽입).": (
        "Arguments may be Korean; they are inserted as shown on screen.",
        "引数には韓国語も使えます(画面の表示どおりに挿入)。",
        "参数可以使用韩文(按屏幕显示原样插入)。"),
}

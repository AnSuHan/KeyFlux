# KeyFlux — 키 입력 자동 변환기

> **v1.0.2**

등록한 트리거(단어/단축어/정규식)를 타이핑하면 지정한 텍스트로 자동
치환해 주는 백그라운드 도구입니다. 메모장·브라우저뿐 아니라 터미널
(PowerShell/cmd/Git Bash)에서도 동작합니다.

## 주요 기능

- **트리거 타입 3종**: `word`(단어), `special`(`;`단축어), `regex`(정규식)
- **특수 변수 치환**: `{date}` `{time}` `{datetime}` (형식 지정: `{date:%Y%m%d}`)
- **한/영·대소문자 무관 매칭** (v1.0.2, 기본 활성화): 트리거를 등록한
  입력 모드(한/영)나 대소문자와 상관없이 **같은 물리 키**를 누르면 동작.
  예) 영문 `abc` 트리거를 한글 모드로 같은 키를 쳐도(→`ㅁㅠㅊ`) 변환됨.
  상단 툴바의 **한/영·대소문자 무관** 체크박스로 끌 수 있음.
- **접두사 겹침 트리거 지원** (v1.0.2): `::d` 와 `::dev` 처럼 짧은 트리거가
  긴 트리거의 접두사여도 둘 다 사용 가능 (긴 트리거 완성 시 그쪽을, 더
  길게 갈 수 없으면 짧은 쪽을 확정).
- **규칙 편집창에서 Enter 로 저장** (v1.0.2)
- 트레이 상주, 드래그로 규칙 순서 변경, JSON 내보내기/불러오기

## 실행 (개발)

```bash
pip install -r requirements.txt
python main.py
```

---

## 설정 파일 (rules.json)

### 내보내기
앱 GUI 상단 툴바 **↑ 내보내기** 버튼 → 원하는 경로에 JSON 저장

### 불러오기
**↓ 불러오기** 버튼 → JSON 선택 → 대체 또는 추가 선택

### 직접 편집
```json
[
  { "type": "word",    "trigger": "abc",    "output": "123",    "enabled": true },
  { "type": "special", "trigger": ";date",  "output": "{date}", "enabled": true },
  { "type": "regex",   "trigger": "\\d{4}", "output": "[YEAR]", "enabled": false }
]
```

특수 변수: `{date}` `{time}` `{datetime}`

---

## 설정 파일 우선순위

| 위치 | 설명 |
|------|------|
| 실행파일(또는 스크립트) 옆 `rules.json` | **최우선** — 동봉 배포용 |
| `~/.keyflux_rules.json` | fallback — 개인 설정 |

동작 옵션(한/영·대소문자 무관 매칭 on/off)은 규칙 파일과 별개로
`rules.json` 옆 `keyflux_settings.json`(없으면 `~/.keyflux_settings.json`)
에 저장됩니다.

---

## 종료 방법

- **트레이 아이콘** 우클릭 → 종료
- **개발 중 터미널에서 실행한 경우**: `Ctrl+C`로 종료 가능 (창이 트레이에 있어도 터미널에서 Ctrl+C 누르면 프로세스 전체 종료)

---

## exe로 빌드하기 (Windows)

### 1. PyInstaller 설치

가상환경을 켠 상태에서:

```powershell
pip install -r requirements.txt
pip install pyinstaller
```

### 2. 빌드 실행

```powershell
python build.py
```

빌드가 끝나면 `dist\KeyFlux.exe`가 생성됩니다. 이 파일 하나만 복사해서 Python이 설치되지 않은 PC에서도 바로 실행할 수 있습니다.

### 3. 특정 규칙(rules.json)을 포함해서 배포하기

미리 원하는 규칙으로 구성한 `rules.json`을 `main.py`와 같은 폴더에 둔 뒤:

```powershell
python build.py --with-rules
```

`dist\KeyFlux.exe`와 `dist\rules.json` **두 파일이 함께 생성**됩니다. 배포할 때 이 두 파일을 같은 폴더에 넣어서 전달하세요 (exe만 옮기면 기본 규칙으로 시작됩니다).

### 4. 직접 PyInstaller 명령으로 빌드하고 싶다면

```powershell
pyinstaller --onefile --windowed --name KeyFlux main.py
```

### 빌드 후 체크리스트

- [ ] `dist\KeyFlux.exe` 더블클릭 시 정상 실행되는지 확인
- [ ] 트레이 아이콘이 나타나는지 확인
- [ ] **Windows Defender/백신이 "알 수 없는 앱"으로 경고**할 수 있음 — 키 입력을 감지하는 프로그램 특성상 흔한 현상입니다. "추가 정보 → 실행" 또는 백신 예외 처리 필요
- [ ] `--with-rules`로 빌드했다면 exe와 rules.json이 같은 폴더에 있는지 확인

---

## 플랫폼별 주의사항

| OS | 필요 조치 |
|----|-----------|
| Windows | 없음 (단, 위 백신 경고 참고) |
| macOS | 시스템 환경설정 → 개인 정보 보호 → 손쉬운 사용 허용 |
| Linux | `sudo usermod -aG input $USER` 후 재로그인 |

---

## 테스트

핵심 로직(정규화 매칭·접두사 겹침 트리거·한글 조합·출력 변수 치환)은
GUI/실제 키 주입 없이 검증하는 단위 테스트가 있습니다.

```bash
python -m unittest discover -s tests -v
```

---

## 변경 이력

### v1.0.2
- **한/영·대소문자 무관 매칭** 옵션 추가 (기본 활성화). 두벌식 키 매핑으로
  입력·트리거를 물리 키 시퀀스로 정규화해 비교 → 입력 모드/대소문자 무관.
- **접두사 겹침 트리거**(`::d` / `::dev`) 둘 다 사용 가능하도록 보류·확정 로직 추가.
- 규칙 편집창에서 **Enter 로 저장**.
- 창/작업표시줄/트레이/대화상자 **앱 아이콘(파비콘)** 지정 + Windows AppUserModelID.
- "이미 실행 중" 다이얼로그가 다른 창 뒤로 **숨지 않도록** 항상-위로 표시.
- 핵심 로직 **단위 테스트**(`tests/`) 추가.

### v1.0.1
- 치환 입력을 유니코드 직접 주입(SendInput)으로 교체 — 터미널 호환.

### v1.0.0
- 최초 릴리스.
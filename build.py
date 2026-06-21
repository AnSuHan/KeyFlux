"""
KeyFlux 빌드 스크립트
  python build.py             -- 기본 빌드 (rules.json 없으면 번들 안 함)
  python build.py --with-rules -- 현재 rules.json 을 exe 에 포함
"""
import os
import re
import sys
import subprocess
import shutil
from pathlib import Path

HERE = Path(__file__).parent
RULES_FILE = HERE / "rules.json"
MAIN_FILE  = HERE / "main.py"
ICON_FILE  = HERE / "keyflux.ico"  # exe/작업표시줄 아이콘(파비콘)


def _app_version() -> str:
    """main.py 의 APP_VERSION 을 읽어온다(=릴리스 태그/파일명 버전)."""
    text = MAIN_FILE.read_text(encoding="utf-8")
    m = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', text)
    return m.group(1) if m else "0.0.0"


# GitHub 배포 시 실행파일명에 버전을 포함한다(예: KeyFlux_v1.0.3.exe).
APP_VERSION = _app_version()
APP_NAME = f"KeyFlux_v{APP_VERSION}"

def run(cmd):
    print("$", " ".join(str(c) for c in cmd))
    result = subprocess.run(cmd, check=True)
    return result

def main():
    include_rules = "--with-rules" in sys.argv

    if include_rules and not RULES_FILE.exists():
        print("[경고] rules.json 이 없습니다. --with-rules 를 무시합니다.")
        include_rules = False

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--windowed",           # 콘솔 창 숨김 (Windows)
        "--name", APP_NAME,     # 버전 포함 파일명 (KeyFlux_v1.0.3)
        "--clean",
    ]

    # exe 파일/작업표시줄 아이콘 지정 (없으면 generate_icon.py 로 생성 안내)
    if ICON_FILE.exists():
        cmd += ["--icon", str(ICON_FILE)]
        # 실행 중 창/작업표시줄/트레이 아이콘도 같은 .ico 를 로드하도록
        # onefile 번들에 포함한다(make_app_icon 이 resource_path 로 찾음).
        cmd += ["--add-data", f"{ICON_FILE}{os.pathsep}."]
    else:
        print("[경고] keyflux.ico 가 없습니다. 'python generate_icon.py' 로 "
              "먼저 아이콘을 생성하면 exe 에 아이콘이 적용됩니다.")

    if include_rules:
        print("[정보] 빌드 후 dist/rules.json 도 함께 복사합니다.")

    cmd.append(str(MAIN_FILE))
    run(cmd)

    # exe 옆에 rules.json 복사 (설정 동봉 배포용)
    dist_dir = HERE / "dist"
    if include_rules and RULES_FILE.exists():
        dest = dist_dir / "rules.json"
        shutil.copy(RULES_FILE, dest)
        print(f"[완료] {dest} 복사됨")

    exe_name = APP_NAME + (".exe" if sys.platform == "win32" else "")
    print("\nBuild complete!")
    print(f"   실행파일: {dist_dir / exe_name}")
    if include_rules:
        print(f"   설정파일: {dist_dir / 'rules.json'}")
        print(f"\n   배포 시 {exe_name} + rules.json 을 함께 전달하세요.")
    else:
        print("\n   설정은 실행 후 홈디렉토리에 자동 저장됩니다.")
        print("   특정 rules.json 을 동봉하려면: python build.py --with-rules")

if __name__ == "__main__":
    main()
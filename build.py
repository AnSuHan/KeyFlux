"""
KeyFlux 빌드 스크립트
  python build.py             -- 기본 빌드 (rules.json 없으면 번들 안 함)
  python build.py --with-rules -- 현재 rules.json 을 exe 에 포함
"""
import sys
import subprocess
import shutil
from pathlib import Path

HERE = Path(__file__).parent
RULES_FILE = HERE / "rules.json"
MAIN_FILE  = HERE / "main.py"

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
        "--name", "KeyFlux",
        "--clean",
    ]

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

    print("\n✅ 빌드 완료!")
    print(f"   실행파일: {dist_dir / 'KeyFlux'}{'.exe' if sys.platform == 'win32' else ''}")
    if include_rules:
        print(f"   설정파일: {dist_dir / 'rules.json'}")
        print("\n   배포 시 KeyFlux.exe + rules.json 을 함께 전달하세요.")
    else:
        print("\n   설정은 실행 후 홈디렉토리에 자동 저장됩니다.")
        print("   특정 rules.json 을 동봉하려면: python build.py --with-rules")

if __name__ == "__main__":
    main()
"""
入口腳本：跑回測 → 產 HTML 報表

用法：
    python main.py
    python main.py --open     # 跑完自動開啟瀏覽器
"""
import argparse
import sys
import webbrowser
from pathlib import Path

from quant import run
from report import save


def main():
    parser = argparse.ArgumentParser(description='FinMind 多因子量化回測')
    parser.add_argument('--open', action='store_true', help='跑完自動開啟報告')
    args = parser.parse_args()

    print("=" * 60)
    print("FinMind 多因子量化回測")
    print("=" * 60)

    try:
        result = run()
    except Exception as e:
        print(f"\n❌ 回測失敗：{e}")
        sys.exit(1)

    save(result)

    if args.open:
        from config import REPORT_FILE
        webbrowser.open(REPORT_FILE.absolute().as_uri())
        print(f"🌐 已開啟瀏覽器")


if __name__ == '__main__':
    main()
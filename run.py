"""
程序入口
双击运行：启动本地 Web 服务，自动打开浏览器
"""

import os
import sys
import time
import socket
import webbrowser
import threading
from pathlib import Path

# 设置控制台输出编码为 UTF-8（解决 Windows GBK 编码问题）
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

# 确保项目根目录在 path 中
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

from pcb_tool import web


def find_free_port(start=5000, end=5010):
    """查找可用端口"""
    for port in range(start, end + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', port))
                return port
        except OSError:
            continue
    return start  # fallback


def safe_print(s):
    """安全的打印函数，避免编码错误"""
    try:
        print(s)
    except UnicodeEncodeError:
        # 把不能编码的字符替换为 ASCII
        print(s.encode('ascii', errors='replace').decode('ascii'))


def main():
    port = find_free_port()

    # 创建输出目录
    os.makedirs(os.path.join(PROJECT_ROOT, 'output'), exist_ok=True)

    safe_print("=" * 60)
    safe_print("  PCB 注释脱敏与回填工具")
    safe_print("=" * 60)
    safe_print(f"  服务地址: http://127.0.0.1:{port}")
    safe_print(f"  工作目录: {PROJECT_ROOT}")
    safe_print("=" * 60)
    safe_print("  正在启动 Web 服务...")

    # 延迟打开浏览器（等服务启动后）
    def open_browser():
        time.sleep(2)
        url = f'http://127.0.0.1:{port}'
        try:
            webbrowser.open(url)
            safe_print(f"  [OK] 已在浏览器中打开: {url}")
        except Exception as e:
            safe_print(f"  [WARN] 无法自动打开浏览器: {e}")
            safe_print(f"  请手动访问: {url}")

    threading.Thread(target=open_browser, daemon=True).start()

    safe_print("  按 Ctrl+C 退出")
    safe_print("=" * 60)

    try:
        web.app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)
    except KeyboardInterrupt:
        safe_print("\n  服务已停止")


if __name__ == '__main__':
    main()

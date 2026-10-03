"""
PyInstaller 打包脚本
将整个应用打包成单文件 EXE
"""
import os
import sys
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
APP_NAME = 'PCB脱敏回填工具'
ENTRY = os.path.join(PROJECT_ROOT, 'run.py')


def build():
    """执行 PyInstaller 打包"""
    os.chdir(PROJECT_ROOT)

    # PyInstaller 命令
    # --onefile: 打包成单文件
    # 不加 --windowed：保留控制台窗口，用户可以看到服务地址和状态
    # --add-data: 包含 templates 和 static 目录
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--name', APP_NAME,
        '--add-data', f'templates{os.pathsep}templates',
        '--add-data', f'static{os.pathsep}static',
        '--noconfirm',
        ENTRY,
    ]

    print('=' * 60)
    print('  开始打包 EXE...')
    print('=' * 60)
    print(f'  入口: {ENTRY}')
    print(f'  名称: {APP_NAME}')
    print('=' * 60)

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)

    if result.returncode == 0:
        exe_path = os.path.join(PROJECT_ROOT, 'dist', f'{APP_NAME}.exe')
        if os.path.exists(exe_path):
            size_mb = os.path.getsize(exe_path) / (1024 * 1024)
            print()
            print('=' * 60)
            print(f'  打包成功')
            print(f'  EXE 路径: {exe_path}')
            print(f'  文件大小: {size_mb:.1f} MB')
            print('=' * 60)
        else:
            print('  打包完成但未找到 EXE 文件')
    else:
        print('  打包失败')
        sys.exit(1)


if __name__ == '__main__':
    build()

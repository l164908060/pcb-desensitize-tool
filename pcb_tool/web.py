"""
Flask Web 应用
提供 PCB 注释脱敏与回填的 Web 界面
"""

import os
import sys
import time
import webbrowser
import threading
from flask import Flask, render_template, request, jsonify, send_file

# 添加项目根目录到 path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from pcb_tool.pcb_processor import desensitize_pcb, fill_from_bom, PcbProcessError
from pcb_tool.pcb_binary import get_pcb_info

app = Flask(__name__, template_folder=os.path.join(PROJECT_ROOT, 'templates'),
            static_folder=os.path.join(PROJECT_ROOT, 'static'))

# 配置
UPLOAD_DIR = os.path.join(PROJECT_ROOT, 'output', 'uploads')
OUTPUT_DIR = os.path.join(PROJECT_ROOT, 'output')
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)
app.config['UPLOAD_DIR'] = UPLOAD_DIR
app.config['OUTPUT_DIR'] = OUTPUT_DIR
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max


def safe_basename(filename: str) -> str:
    """
    安全文件名处理：只取 basename 并去掉路径分隔符和控制字符，保留中文

    参数:
        filename: 原始文件名（可能含路径或特殊字符）
    返回:
        清理后的文件名；非法时返回空字符串
    说明:
        不用 werkzeug 的 secure_filename，因为它会剥掉所有非 ASCII 字符，
        导致含中文的输出文件名（如 *_脱敏_*.PcbDoc）下载时 404
    """
    name = filename.replace('\\', '/').split('/')[-1]
    name = name.replace('\x00', '').strip()
    if name in ('', '.', '..'):
        return ''
    return name


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/preview', methods=['POST'])
def preview_pcb():
    """预览 PCB 文件信息：元件列表、当前 Comment"""
    if 'pcb_file' not in request.files:
        return jsonify({'success': False, 'error': '未选择 PCB 文件'}), 400

    pcb_file = request.files['pcb_file']
    if not pcb_file.filename:
        return jsonify({'success': False, 'error': '文件名为空'}), 400

    # 保存上传的文件
    filename = safe_basename(pcb_file.filename)
    if not filename or not filename.lower().endswith('.pcbdoc'):
        return jsonify({'success': False, 'error': '请上传 .PcbDoc 文件'}), 400

    timestamp = str(int(time.time() * 1000))
    saved_name = f'{timestamp}_{filename}'
    saved_path = os.path.join(UPLOAD_DIR, saved_name)
    pcb_file.save(saved_path)

    try:
        info = get_pcb_info(saved_path)
        return jsonify({
            'success': True,
            'saved_filename': saved_name,
            'component_count': info['component_count'],
            'components': info['components'],
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'解析 PCB 失败: {str(e)}'}), 500


@app.route('/api/desensitize', methods=['POST'])
def api_desensitize():
    """一键脱敏：清除所有 Comment"""
    data = request.get_json()
    if not data or 'saved_filename' not in data:
        return jsonify({'success': False, 'error': '参数错误'}), 400

    saved_path = os.path.join(UPLOAD_DIR, data['saved_filename'])
    if not os.path.exists(saved_path):
        return jsonify({'success': False, 'error': '文件不存在，请重新上传'}), 404

    try:
        result = desensitize_pcb(saved_path, OUTPUT_DIR)
        return jsonify({
            'success': True,
            'cleared_count': result.success_count,
            'output_filename': os.path.basename(result.output_path),
            'message': f'已清除 {result.success_count} 条 Comment',
        })
    except PcbProcessError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'处理失败: {str(e)}'}), 500


@app.route('/api/fill', methods=['POST'])
def api_fill():
    """一键回填：从 BOM 写入 Comment"""
    pcb_file = request.files.get('pcb_file')
    bom_file = request.files.get('bom_file')

    if not pcb_file or not bom_file:
        return jsonify({'success': False, 'error': '请同时上传 PCB 和 BOM 文件'}), 400

    if not pcb_file.filename or not bom_file.filename:
        return jsonify({'success': False, 'error': '文件名不能为空'}), 400

    # 保存上传文件
    timestamp = str(int(time.time() * 1000))
    pcb_name = safe_basename(pcb_file.filename)
    bom_name = safe_basename(bom_file.filename)
    if not pcb_name or not bom_name:
        return jsonify({'success': False, 'error': '文件名非法'}), 400
    pcb_path = os.path.join(UPLOAD_DIR, f'{timestamp}_{pcb_name}')
    bom_path = os.path.join(UPLOAD_DIR, f'{timestamp}_{bom_name}')
    pcb_file.save(pcb_path)
    bom_file.save(bom_path)

    try:
        result = fill_from_bom(pcb_path, bom_path, OUTPUT_DIR)
        response = {
            'success': True,
            'success_count': result.success_count,
            'failed_designators': result.failed_designators,
            'warnings': result.warnings,
            'output_filename': os.path.basename(result.output_path),
            # 校验报告（每个位号一行：改前/改后 Comment、封装、BOM 状态、写入状态等）
            'audit_rows': result.audit_rows,
            'message': f'已写入 {result.success_count} 个元件的 Comment',
        }
        if result.failed_designators:
            response['message'] += f'，{len(result.failed_designators)} 个失败'
        return jsonify(response)
    except PcbProcessError as e:
        return jsonify({'success': False, 'error': str(e)}), 400
    except Exception as e:
        return jsonify({'success': False, 'error': f'处理失败: {str(e)}'}), 500


@app.route('/api/download/<filename>')
def download_file(filename):
    """下载处理后的文件"""
    safe_name = safe_basename(filename)
    if not safe_name:
        return jsonify({'success': False, 'error': '文件名非法'}), 400
    file_path = os.path.join(OUTPUT_DIR, safe_name)
    if not os.path.exists(file_path):
        return jsonify({'success': False, 'error': '文件不存在'}), 404
    return send_file(file_path, as_attachment=True, download_name=safe_name)


def open_browser(port):
    """延迟打开浏览器"""
    time.sleep(1.5)
    webbrowser.open(f'http://127.0.0.1:{port}')


def main(port=5000, open_browser_flag=True):
    """启动 Web 服务"""
    if open_browser_flag:
        threading.Thread(target=open_browser, args=(port,), daemon=True).start()
    app.run(host='127.0.0.1', port=port, debug=False, use_reloader=False)


if __name__ == '__main__':
    main()

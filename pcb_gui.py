"""
PCB 注释脱敏与回填工具 — 桌面 GUI 版（Tkinter）

双击 EXE 直接运行，原生窗口界面，不依赖浏览器。
功能：
  - 一键脱敏：清除 PcbDoc 中所有元件的 Comment（元件参数）
  - 一键回填：先清空全部 Comment，再从 BOM 元件清单写入（严格模式，以 BOM 为准）
界面底部版权：佳文电子 版权所有
"""

import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from pcb_tool.pcb_processor import (
    desensitize_pcb, fill_from_bom, PcbProcessError,
)
from pcb_tool.bom_parser import BomParseError
from pcb_tool.pcb_binary import get_pcb_info

APP_TITLE = 'PCB 注释脱敏与回填工具'
COPYRIGHT_TEXT = '佳文电子 版权所有'


# =================== 通用工具 ===================

def run_in_thread(root, job, on_done):
    """
    在后台线程执行耗时任务，避免界面卡死
    参数:
        root: Tk 根窗口（用于 after 调度）
        job: 无参可调用对象，在后台线程中执行
        on_done: 回调 fn(status, payload)；status 为 'ok' 时 payload 是 job 返回值，
                 为 'err' 时 payload 是异常对象
    返回:
        无
    """
    result_q = queue.Queue()

    def worker():
        """后台工作线程：执行 job 并把结果放入队列"""
        try:
            result_q.put(('ok', job()))
        except Exception as e:  # noqa: BLE001 - 统一交给主线程展示
            result_q.put(('err', e))

    def poll():
        """主线程轮询队列，任务完成后回调 on_done"""
        try:
            status, payload = result_q.get_nowait()
            on_done(status, payload)
        except queue.Empty:
            root.after(100, poll)

    threading.Thread(target=worker, daemon=True).start()
    root.after(100, poll)


def suggest_output_path(src_path, suffix):
    """
    生成"另存为"对话框的默认文件名
    参数:
        src_path: 源文件完整路径
        suffix: 输出后缀（如 '_desensitized' / '_refilled'）
    返回:
        建议的输出文件完整路径（同目录、同主名、加后缀）
    """
    base, ext = os.path.splitext(src_path)
    return base + suffix + (ext or '.PcbDoc')


def make_tree(parent, columns, heights=12):
    """
    构造带滚动条的 ttk.Treeview 表格
    参数:
        parent: 父容器
        columns: 列定义列表 [(列id, 列标题, 宽度), ...]
        heights: 可视行数
    返回:
        (frame, tree) - 外框和表格控件
    """
    frame = ttk.Frame(parent)
    ybar = ttk.Scrollbar(frame, orient='vertical')
    tree = ttk.Treeview(
        frame, columns=[c[0] for c in columns],
        show='headings', height=heights, yscrollcommand=ybar.set,
    )
    ybar.config(command=tree.yview)
    for col_id, col_title, width in columns:
        tree.heading(col_id, text=col_title)
        tree.column(col_id, width=width, anchor='w')
    tree.pack(side='left', fill='both', expand=True)
    ybar.pack(side='right', fill='y')
    return frame, tree


# =================== 主应用 ===================

class App(tk.Tk):
    """主窗口：两个标签页（脱敏 / 回填）+ 底部版权栏"""

    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry('1000x720')
        self.minsize(860, 600)

        self._pcb_des_path = ''   # 脱敏页选中的 PcbDoc 路径
        self._pcb_fill_path = ''  # 回填页选中的 PcbDoc 路径
        self._bom_path = ''       # 回填页选中的 BOM 路径

        self._build_style()
        self._build_layout()

    # ---------- 界面构建 ----------

    def _build_style(self):
        """配置全局 ttk 样式（字体、表格行高）"""
        style = ttk.Style(self)
        try:
            style.theme_use('clam')
        except tk.TclError:
            pass
        default_font = ('Microsoft YaHei UI', 10)
        self.option_add('*Font', default_font)
        style.configure('Treeview', rowheight=26, font=('Microsoft YaHei UI', 10))
        style.configure('Treeview.Heading', font=('Microsoft YaHei UI', 10, 'bold'))
        style.configure('Title.TLabel', font=('Microsoft YaHei UI', 15, 'bold'))
        style.configure('Sub.TLabel', foreground='#666666')
        style.configure('Action.TButton', font=('Microsoft YaHei UI', 11, 'bold'),
                        padding=(18, 8))

    def _build_layout(self):
        """搭建整体布局：标题区 + 标签页 + 底部版权栏（grid 布局保证底部固定）"""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=0)   # 标题行
        self.rowconfigure(1, weight=1)   # 标签页（占满中间）
        self.rowconfigure(2, weight=0)   # 版权栏

        # 标题行
        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky='ew', padx=16, pady=(12, 4))
        ttk.Label(header, text='🔧 ' + APP_TITLE, style='Title.TLabel').pack(anchor='w')
        ttk.Label(header, text='Altium Designer PcbDoc 文件批量处理 · 一键清除 / 导入元件参数',
                  style='Sub.TLabel').pack(anchor='w')

        # 中间标签页
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(row=1, column=0, sticky='nsew', padx=16, pady=8)
        self._build_desensitize_tab()
        self._build_fill_tab()

        # 底部版权栏（grid row=2 固定不动）
        footer = ttk.Frame(self, relief='ridge', borderwidth=2)
        footer.grid(row=2, column=0, sticky='ew')
        ttk.Label(
            footer, text=COPYRIGHT_TEXT,
            font=('Microsoft YaHei UI', 10, 'bold'),
            foreground='#555555', anchor='center',
        ).pack(fill='x', ipadx=8, ipady=4)

    def _build_desensitize_tab(self):
        """构建"一键脱敏"标签页"""
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='  🛡️ 一键脱敏  ')

        # 文件选择行
        row = ttk.Frame(tab)
        row.pack(fill='x', pady=(0, 8))
        ttk.Button(row, text='选择 PcbDoc 文件…',
                   command=self._pick_pcb_des).pack(side='left')
        self.lbl_pcb_des = ttk.Label(row, text='（未选择文件）', foreground='#999999')
        self.lbl_pcb_des.pack(side='left', padx=10)

        # 预览区
        self.lbl_des_preview = ttk.Label(tab, text='')
        self.lbl_des_preview.pack(anchor='w', pady=(0, 4))
        cols = [('des', '位号', 90), ('comment', '当前 Comment', 220), ('pattern', '封装', 180)]
        frame, self.tree_des = make_tree(tab, cols, heights=14)
        frame.pack(fill='both', expand=True, pady=(0, 8))
        # 状态行着色：有 Comment 的正常，空的不特殊标
        self.tree_des.tag_configure('empty', foreground='#999999')

        # 执行按钮
        self.btn_desensitize = ttk.Button(
            tab, text='🛡️ 执行脱敏', style='Action.TButton',
            command=self._do_desensitize, state='disabled')
        self.btn_desensitize.pack(anchor='w', pady=(0, 6))

        self.lbl_des_status = ttk.Label(tab, text='', foreground='#2e7d32')
        self.lbl_des_status.pack(anchor='w')

    def _build_fill_tab(self):
        """构建"一键回填"标签页（含审计报告表格）"""
        tab = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(tab, text='  📥 一键回填  ')

        # 文件选择行
        row = ttk.Frame(tab)
        row.pack(fill='x', pady=(0, 8))
        ttk.Button(row, text='选择 PcbDoc 文件…',
                   command=self._pick_pcb_fill).pack(side='left')
        self.lbl_pcb_fill = ttk.Label(row, text='（未选择文件）', foreground='#999999')
        self.lbl_pcb_fill.pack(side='left', padx=10)
        ttk.Button(row, text='选择 BOM Excel 文件…',
                   command=self._pick_bom).pack(side='left', padx=(16, 0))
        self.lbl_bom = ttk.Label(row, text='（未选择文件）', foreground='#999999')
        self.lbl_bom.pack(side='left', padx=10)

        hint = ttk.Label(
            tab, text='回填为严格模式：先清空 PCB 全部元件参数，再写入 BOM 中的参数；'
                      'BOM 里没有的位号保持空。',
            foreground='#1565c0')
        hint.pack(anchor='w', pady=(0, 6))

        # 执行按钮
        self.btn_fill = ttk.Button(
            tab, text='📥 执行回填', style='Action.TButton',
            command=self._do_fill, state='disabled')
        self.btn_fill.pack(anchor='w', pady=(0, 6))

        self.lbl_fill_status = ttk.Label(tab, text='', foreground='#2e7d32')
        self.lbl_fill_status.pack(anchor='w', pady=(0, 4))

        # 审计报告表格
        self.lbl_audit_summary = ttk.Label(tab, text='', font=('Microsoft YaHei UI', 10, 'bold'))
        self.lbl_audit_summary.pack(anchor='w', pady=(0, 4))
        cols = [
            ('des', '位号', 70), ('pattern', '封装', 130), ('bom', 'BOM 元件值', 140),
            ('before', '改前 Comment', 150), ('after', '改后 Comment', 150),
            ('bomst', 'BOM 状态', 80), ('wst', '写入状态', 80), ('reason', '说明', 200),
        ]
        frame, self.tree_audit = make_tree(tab, cols, heights=13)
        frame.pack(fill='both', expand=True)
        # 状态着色
        self.tree_audit.tag_configure('ok', background='#e8f5e9')       # 成功：绿
        self.tree_audit.tag_configure('fail', background='#ffebee')     # 失败：红
        self.tree_audit.tag_configure('cleared', background='#fffde7')  # 清空：黄
        self.tree_audit.tag_configure('miss', background='#fff3e0')     # BOM 缺失：橙

    # ---------- 事件处理：文件选择 ----------

    def _pick_pcb_des(self):
        """脱敏页：选择 PcbDoc 文件并加载预览"""
        path = filedialog.askopenfilename(
            title='选择 PcbDoc 文件',
            filetypes=[('PcbDoc 文件', '*.PcbDoc *.pcbdoc'), ('所有文件', '*.*')])
        if not path:
            return
        self._pcb_des_path = path
        self.lbl_pcb_des.config(text=os.path.basename(path), foreground='#000000')
        self.lbl_des_preview.config(text='正在解析…')
        self._clear_tree(self.tree_des)
        self.btn_desensitize.config(state='disabled')
        run_in_thread(self, lambda: get_pcb_info(path), self._on_des_preview)

    def _pick_pcb_fill(self):
        """回填页：选择 PcbDoc 文件"""
        path = filedialog.askopenfilename(
            title='选择 PcbDoc 文件',
            filetypes=[('PcbDoc 文件', '*.PcbDoc *.pcbdoc'), ('所有文件', '*.*')])
        if not path:
            return
        self._pcb_fill_path = path
        self.lbl_pcb_fill.config(text=os.path.basename(path), foreground='#000000')
        self._update_fill_button()

    def _pick_bom(self):
        """回填页：选择 BOM Excel 文件"""
        path = filedialog.askopenfilename(
            title='选择 BOM Excel 文件',
            filetypes=[('Excel 文件', '*.xlsx *.xls'), ('所有文件', '*.*')])
        if not path:
            return
        self._bom_path = path
        self.lbl_bom.config(text=os.path.basename(path), foreground='#000000')
        self._update_fill_button()

    def _update_fill_button(self):
        """PCB 和 BOM 都已选择时启用回填按钮"""
        ready = bool(self._pcb_fill_path and self._bom_path)
        self.btn_fill.config(state='normal' if ready else 'disabled')

    # ---------- 事件处理：脱敏 ----------

    def _on_des_preview(self, status, payload):
        """脱敏页：预览解析完成的回调"""
        if status == 'err':
            self.lbl_des_preview.config(text='')
            messagebox.showerror('解析失败', str(payload))
            return
        info = payload
        self.lbl_des_preview.config(
            text=f'共 {info["component_count"]} 个元件（双击列表可核对当前参数）')
        for comp in info['components']:
            comment = comp.get('current_comment') or ''
            tag = 'empty' if not comment.strip() else ''
            self.tree_des.insert('', 'end', values=(
                comp['designator'], comment or '(空)', comp.get('pattern', '')), tags=(tag,))
        self.btn_desensitize.config(state='normal')

    def _do_desensitize(self):
        """脱敏页：执行脱敏（先选保存位置再处理）"""
        if not self._pcb_des_path:
            return
        out = filedialog.asksaveasfilename(
            title='脱敏结果另存为',
            defaultextension='.PcbDoc',
            initialfile=os.path.basename(suggest_output_path(self._pcb_des_path, '_desensitized')),
            filetypes=[('PcbDoc 文件', '*.PcbDoc')])
        if not out:
            return
        self.btn_desensitize.config(state='disabled')
        self.lbl_des_status.config(text='正在清除 Comment…', foreground='#666666')
        run_in_thread(
            self,
            lambda: desensitize_pcb(self._pcb_des_path, output_path=out),
            lambda s, p: self._on_des_done(s, p, out))

    def _on_des_done(self, status, payload, out_path):
        """脱敏页：处理完成的回调"""
        self.btn_desensitize.config(state='normal')
        if status == 'err':
            self.lbl_des_status.config(text='', foreground='#2e7d32')
            messagebox.showerror('脱敏失败', str(payload))
            return
        self.lbl_des_status.config(
            text=f'✓ 完成：已清除 {payload.success_count} 条 Comment → {out_path}',
            foreground='#2e7d32')

    # ---------- 事件处理：回填 ----------

    def _do_fill(self):
        """回填页：执行回填（先选保存位置，再清空+写入，完成后显示审计报告）"""
        if not (self._pcb_fill_path and self._bom_path):
            return
        out = filedialog.asksaveasfilename(
            title='回填结果另存为',
            defaultextension='.PcbDoc',
            initialfile=os.path.basename(suggest_output_path(self._pcb_fill_path, '_refilled')),
            filetypes=[('PcbDoc 文件', '*.PcbDoc')])
        if not out:
            return
        self.btn_fill.config(state='disabled')
        self.lbl_fill_status.config(text='正在清空并写入 Comment…', foreground='#666666')
        self._clear_tree(self.tree_audit)
        run_in_thread(
            self,
            lambda: fill_from_bom(self._pcb_fill_path, self._bom_path, output_path=out),
            lambda s, p: self._on_fill_done(s, p, out))

    def _on_fill_done(self, status, payload, out_path):
        """回填页：处理完成的回调（渲染审计报告表格）"""
        self.btn_fill.config(state='normal')
        if status == 'err':
            self.lbl_fill_status.config(text='', foreground='#2e7d32')
            msg = str(payload)
            messagebox.showerror('回填失败', msg)
            return

        self.lbl_fill_status.config(
            text=f'✓ 完成：成功 {payload.success_count} 个 → {out_path}',
            foreground='#2e7d32')

        # 统计
        rows = payload.audit_rows or []
        counts = {'成功': 0, '失败': 0, '清空': 0, '缺失': 0}
        for r in rows:
            counts[r['write_status']] = counts.get(r['write_status'], 0) + 1
            counts[r['bom_status']] = counts.get(r['bom_status'], 0) + 1
        self.lbl_audit_summary.config(
            text=f'📋 回填校验报告：共 {len(rows)} 个位号，'
                 f'成功 {counts["成功"]}，失败 {counts["失败"]}，'
                 f'清空（BOM 无参数）{counts["清空"]}，BOM 缺失 {counts["缺失"]}')

        # 表格行
        for r in rows:
            tag = self._audit_row_tag(r)
            self.tree_audit.insert('', 'end', tags=(tag,), values=(
                r['designator'], r.get('pattern', ''), r.get('bom_value', ''),
                r.get('before_comment', ''), r.get('after_comment', ''),
                r.get('bom_status', ''), r.get('write_status', ''), r.get('reason', '')))

        # 有失败项时给出醒目提示
        if payload.failed_designators:
            messagebox.showwarning(
                '部分参数写入失败',
                f'以下 {len(payload.failed_designators)} 个位号的新参数超出原 Comment 空间，'
                f'未能写入（详见校验报告）：\n\n'
                + '、'.join(payload.failed_designators))

    @staticmethod
    def _audit_row_tag(row):
        """
        把审计行映射到表格着色 tag
        参数:
            row: 审计行字典
        返回:
            tag 名（ok / fail / cleared / miss）
        """
        if row['write_status'] == '失败':
            return 'fail'
        if row['write_status'] == '成功':
            return 'ok'
        if row['bom_status'] == '缺失':
            return 'miss'
        return 'cleared'

    # ---------- 工具 ----------

    @staticmethod
    def _clear_tree(tree):
        """清空 Treeview 的全部行"""
        for iid in tree.get_children():
            tree.delete(iid)


def main():
    """程序入口：创建主窗口并进入消息循环"""
    app = App()
    app.mainloop()


if __name__ == '__main__':
    main()

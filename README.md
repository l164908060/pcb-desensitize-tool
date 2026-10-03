# PCB 脱敏回填工具

Altium Designer PcbDoc 文件**一键脱敏 + BOM 回填**工具。交付 PCB 制造商前清除设计注释（Comment）等敏感信息，打样回来后再从 BOM Excel 一键回填，全程不打开 AD。

提供两种界面（同一套核心引擎）：

- **Tkinter GUI**（`pcb_gui.py`）：双击运行，无浏览器依赖
- **Flask Web**（`run.py` + `web.py`）：自动选端口并打开浏览器

支持 PyInstaller 打包为独立 EXE（`build_exe.py` / `*.spec`）。

## 功能

- **脱敏**：清空 Components6 流中的 Comment 字段（先解析预览 → 确认 → 清除输出）
- **回填**：从 BOM Excel 按位号写回 Comment，**严格模式**——BOM 中缺失的位号留空并明确报错列出（如 U12 在 PCB 实为 Y12 之类的错位必被检出）
- 预览 / 脱敏 / 回填全程 API 化，处理结果可 round-trip 校验

## 技术要点（二进制解析引擎 `pcb_tool/pcb_binary.py`）

- 直接解析 Altium PcbDoc（OLE/CFB 复合文档）二进制格式，不依赖 AD 安装
- **mini-FAT 支持**：小于 4096 字节的流走 mini-stream 容器，普通 FAT 偏移会差 12 万+ 字节
- **WideStrings6 反查模式**：真实 Comment 在 WideStrings6 中位于 Designator 的"前一条"，以 Components6 的 SOURCEDESIGNATOR 为权威位号集反查定位，兼容布局 A/B 两种流布局
- 编码：Components6 的 PATTERN/Comment 字段为 **GBK**（简体中文版），WideStrings6/Data 为 **UTF-16LE**，布局 `[4B索引][4B长度][字符串+NUL]`
- fallback 链：反查失败时回退 SOURCELIBREFERENCE；`safe_print` + UTF-8 重配置防控制台 UnicodeEncodeError

## 文件说明

| 文件 | 说明 |
|------|------|
| `pcb_gui.py` | Tkinter GUI 主程序 |
| `pcb_tool/` | 核心模块：`pcb_binary.py` 二进制引擎 / `bom_parser.py` BOM 解析 / `pcb_processor.py` 处理逻辑 / `web.py` Flask 应用 |
| `run.py` / `build_exe.py` / `*.spec` | 启动入口 / PyInstaller 打包脚本与配置 |
| `static/` `templates/` | Web UI 前端（app.js / style.css / index.html） |
| `新执行器202608.PcbDoc` / `.xls` | 测试用 PCB 与 BOM（4.6MB，私有仓库仅自用） |
| `程序要求说明.doc` | 原始需求文档 |
| `.workbuddy/memory/*.md` | 开发日志（打包验证、mini-FAT 布局 bug 修复等完整记录） |

## 打包

```bash
python build_exe.py        # 产物：dist/PCB脱敏回填工具.exe
```

注意：打包前必须清掉所有 `__pycache__`（缓存污染会冻结旧字节码）；EXE 不入 git。

---

**佳文电子 版权所有**

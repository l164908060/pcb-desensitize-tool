"""
BOM 解析模块
解析元件清单 Excel（.xlsx）文件
格式要求：
  - 第 1 行：表头
  - 列 A：元件参数（Comment）
  - 列 B：位号（Designator，多个用逗号或空格分隔）
  - 可选列 C：封装
  - 可选列 D：数量
"""

from dataclasses import dataclass
from typing import List, Optional
import os
import shutil
import tempfile
import openpyxl


@dataclass
class BomRow:
    """BOM 中的一行（一个元件分组）"""
    comment: str            # 元件参数
    designators: List[str]  # 该组的所有位号
    package: str            # 封装（可选）
    quantity: int           # 数量（可选）


class BomParseError(Exception):
    """BOM 解析错误"""
    pass


def _ensure_xlsx(xlsx_path: str) -> str:
    """
    确保文件是 openpyxl 可读的 xlsx 格式
    有些 .xls 后缀文件实际是 xlsx（OOXML）格式（常见于 WPS 或在线工具导出）
    如果是这种情况，复制为 .xlsx 临时文件供 openpyxl 读取
    """
    if xlsx_path.lower().endswith('.xlsx'):
        return xlsx_path

    # 尝试作为 ZIP 打开（xlsx 实际是 ZIP）
    import zipfile
    try:
        with zipfile.ZipFile(xlsx_path, 'r'):
            pass  # 能打开说明是 ZIP
    except zipfile.BadZipFile:
        raise BomParseError(
            f"文件 {xlsx_path} 不是有效的 Excel 格式（既不是 .xlsx 也不是旧版 .xls）"
        )

    # 是 ZIP 格式但扩展名是 .xls，复制为 .xlsx
    tmp = tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False)
    tmp.close()
    shutil.copy2(xlsx_path, tmp.name)
    return tmp.name


def parse_bom(xlsx_path: str) -> List[BomRow]:
    """
    解析 BOM Excel 文件
    自动识别列位置（元件参数、位号、封装、数量）
    """
    xlsx_path = _ensure_xlsx(xlsx_path)
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active

    # 读取表头
    headers = []
    for cell in ws[1]:
        if cell.value is not None:
            headers.append(str(cell.value).strip())
        else:
            headers.append('')

    # 识别关键列
    col_comment = _find_column(headers, ['元件参数', '参数', 'Comment', 'Value', '值', '标称值'])
    col_designator = _find_column(headers, ['位号', 'Designator', 'Ref', 'Reference', '标号', '序号'])
    col_package = _find_column(headers, ['封装', 'Package', 'Footprint', 'PCB封装'])
    col_qty = _find_column(headers, ['数量', 'Quantity', 'Qty', '个数'])

    if col_comment is None:
        raise BomParseError("未找到'元件参数'列，请确认表头包含'元件参数'或类似名称")
    if col_designator is None:
        raise BomParseError("未找到'位号'列，请确认表头包含'位号'或类似名称")

    rows = []
    for row_idx in range(2, ws.max_row + 1):
        comment_val = ws.cell(row=row_idx, column=col_comment + 1).value
        des_val = ws.cell(row=row_idx, column=col_designator + 1).value
        pkg_val = ws.cell(row=row_idx, column=col_package + 1).value if col_package is not None else None
        qty_val = ws.cell(row=row_idx, column=col_qty + 1).value if col_qty is not None else None

        comment = str(comment_val).strip() if comment_val is not None else ''
        des_raw = str(des_val).strip() if des_val is not None else ''

        if not comment and not des_raw:
            continue  # 跳过空行

        # 拆分位号（支持中英文逗号、空格、换行分隔）
        designators = [d.strip() for d in des_raw.replace('，', ',').replace('\n', ',').split(',') if d.strip()]
        package = str(pkg_val).strip() if pkg_val is not None else ''
        try:
            quantity = int(qty_val) if qty_val is not None else len(designators)
        except (ValueError, TypeError):
            quantity = len(designators)

        rows.append(BomRow(
            comment=comment,
            designators=designators,
            package=package,
            quantity=quantity,
        ))

    return rows


def _find_column(headers: list, candidates: list) -> Optional[int]:
    """在表头中查找匹配候选关键词的列"""
    for i, h in enumerate(headers):
        for c in candidates:
            if c in h or h in c:
                return i
    return None


def validate_bom(rows: List[BomRow]) -> List[str]:
    """
    校验 BOM 数据，返回错误信息列表（空列表表示无错误）
    检查项：
      - 位号重复
      - 元件参数为空
    """
    errors = []
    seen_designators = {}

    for row_idx, row in enumerate(rows, start=2):  # Excel 行号从 2 开始（第 1 行是表头）
        # 检查元件参数是否为空
        if not row.comment:
            for des in row.designators:
                errors.append(f"第 {row_idx} 行：位号 {des} 的元件参数为空")

        # 检查位号重复
        for des in row.designators:
            if des in seen_designators:
                errors.append(f"位号 {des} 重复：第 {row_idx} 行 和 第 {seen_designators[des]} 行")
            else:
                seen_designators[des] = row_idx

    return errors


def build_designator_to_comment_map(rows: List[BomRow]) -> dict:
    """
    构建位号 → 元件参数 的映射
    """
    mapping = {}
    for row in rows:
        if not row.comment:
            continue
        for des in row.designators:
            mapping[des] = row.comment
    return mapping

"""
PcbDoc 处理器
统一接口：脱敏（清除 Comment）和回填（从 BOM 写入 Comment）
"""

import os
import time
from typing import List
from .pcb_binary import (
    find_widestrings_offset,
    clear_all_comments as _clear_all_comments,
    set_comment as _set_comment,
    get_pcb_info,
    parse_widestrings,
    build_comment_designator_map,
)
from .bom_parser import parse_bom, validate_bom, build_designator_to_comment_map


class PcbProcessError(Exception):
    """PCB 处理错误"""
    pass


class ProcessResult:
    """处理结果"""
    def __init__(self):
        self.success_count = 0
        self.failed_designators: List[str] = []
        self.warnings: List[str] = []
        self.output_path: str = ''
        # 回填校验报告：每个位号一行（含改前/改后 Comment、状态、原因）
        self.audit_rows: List[dict] = []

    def to_dict(self):
        return {
            'success_count': self.success_count,
            'failed_designators': self.failed_designators,
            'warnings': self.warnings,
            'output_path': self.output_path,
            'audit_rows': self.audit_rows,
        }


def desensitize_pcb(pcb_path: str, output_dir: str = None,
                    output_path: str = None) -> ProcessResult:
    """
    一键脱敏：清除 PcbDoc 中所有元件的 Comment 字符串
    生成新文件，原文件保持不变

    参数:
        pcb_path: 输入 PcbDoc 文件路径
        output_dir: 输出目录（默认与输入文件同目录；output_path 优先）
        output_path: 完整输出文件路径（GUI"另存为"场景使用）
    """
    result = ProcessResult()

    if not os.path.exists(pcb_path):
        raise PcbProcessError(f"文件不存在: {pcb_path}")

    # 准备输出路径
    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    else:
        if output_dir is None:
            output_dir = os.path.dirname(pcb_path)
        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(pcb_path))[0]
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        # 输出文件名只用 ASCII（避免 360 浏览器对中文 Content-Disposition 解析异常导致下载失败）
        output_filename = f"{base_name}_desensitized_{timestamp}.PcbDoc"
        output_path = os.path.join(output_dir, output_filename)
    result.output_path = output_path

    # 读取原始文件
    with open(pcb_path, 'rb') as f:
        raw_data = bytearray(f.read())

    # 定位 WideStrings6 数据
    ws_offset, ws_total_size = find_widestrings_offset(bytes(raw_data))

    # 获取 PCB 位号列表（用于反查 Comment）
    pcb_info = get_pcb_info(pcb_path)
    all_designators = [c['designator'] for c in pcb_info['components']]

    # 清除所有 Comment
    raw_data, cleared_count = _clear_all_comments(
        raw_data, ws_offset, ws_total_size, all_designators
    )
    result.success_count = cleared_count

    # 写入新文件
    with open(output_path, 'wb') as f:
        f.write(raw_data)

    return result


def fill_from_bom(pcb_path: str, bom_path: str, output_dir: str = None,
                  output_path: str = None) -> ProcessResult:
    """
    一键回填（严格模式）：先清空 PcbDoc 全部 Comment，再从 BOM 写入

    处理流程：
      1. 清空所有元件的 Comment（与脱敏一致）
      2. 从 BOM 读取元件参数，逐位号写入
      3. BOM 中没有的位号保持空（以 BOM 为准，不残留旧值）
      审计报告的"改前 Comment"记录的是清空前的原始值，便于对照

    参数:
        pcb_path: PcbDoc 文件路径
        bom_path: BOM Excel 文件路径
        output_dir: 输出目录（默认与输入文件同目录；output_path 优先）
        output_path: 完整输出文件路径（GUI"另存为"场景使用）
    """
    result = ProcessResult()

    if not os.path.exists(pcb_path):
        raise PcbProcessError(f"PCB 文件不存在: {pcb_path}")
    if not os.path.exists(bom_path):
        raise PcbProcessError(f"BOM 文件不存在: {bom_path}")

    # 解析 BOM
    bom_rows = parse_bom(bom_path)
    bom_errors = validate_bom(bom_rows)
    if bom_errors:
        raise PcbProcessError("BOM 数据校验失败:\n" + "\n".join(bom_errors))

    des_to_comment = build_designator_to_comment_map(bom_rows)

    # 获取 PCB 元件列表（包含当前 Comment，用于改前对照）
    pcb_info = get_pcb_info(pcb_path)
    pcb_comps_by_des = {c['designator']: c for c in pcb_info['components']}
    pcb_designators = set(pcb_comps_by_des.keys())
    bom_designators = set(des_to_comment.keys())

    # 检查 BOM 中是否有 PCB 找不到的位号
    missing_in_pcb = [des for des in des_to_comment if des not in pcb_designators]
    if missing_in_pcb:
        raise PcbProcessError(
            f"以下位号在 BOM 中存在但 PCB 中找不到: {', '.join(missing_in_pcb)}"
        )

    # 准备输出
    if output_path:
        os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    else:
        if output_dir is None:
            output_dir = os.path.dirname(pcb_path)
        os.makedirs(output_dir, exist_ok=True)
        base_name = os.path.splitext(os.path.basename(pcb_path))[0]
        timestamp = time.strftime('%Y%m%d_%H%M%S')
        # 输出文件名只用 ASCII（避免 360 浏览器对中文 Content-Disposition 解析异常导致下载失败）
        output_filename = f"{base_name}_refilled_{timestamp}.PcbDoc"
        output_path = os.path.join(output_dir, output_filename)
    result.output_path = output_path

    # 读取原始文件
    with open(pcb_path, 'rb') as f:
        raw_data = bytearray(f.read())

    ws_offset, _ws_total_size = find_widestrings_offset(bytes(raw_data))

    # 构建位号→Comment prev 映射，用于取出每位的"改前 Comment"
    ws_data = bytes(raw_data[ws_offset:ws_offset + _ws_total_size])
    ws_entries = parse_widestrings(ws_data)
    cd_map = build_comment_designator_map(ws_entries, list(pcb_comps_by_des.keys()))

    # 严格模式第一步：先清空全部 Comment（BOM 缺失的位号最终保持空）
    # 注意 pcb_info 是从磁盘原文件读的，"改前 Comment"仍为原始值
    raw_data, cleared_count = _clear_all_comments(
        raw_data, ws_offset, _ws_total_size, list(pcb_comps_by_des.keys())
    )

    # 逐个写入 Comment 并产出审计行
    audit_rows: List[dict] = []
    for designator in sorted(pcb_comps_by_des.keys()):
        comp = pcb_comps_by_des[designator]
        # BOM 元件参数（Comment）—— 没有则视为跳过
        new_comment = des_to_comment.get(designator)
        # PCB 中当前的 Comment（改前）
        before_text = comp.get('current_comment', '') or ''

        # 默认状态
        row = {
            'designator': designator,
            'pattern': comp.get('pattern', '') or '',
            'bom_value': new_comment or '',
            'bom_status': '匹配' if new_comment else '缺失',
            'before_comment': before_text,
            'after_comment': new_comment if new_comment else before_text,
            'write_status': '跳过',
            'reason': '',
        }

        if not new_comment:
            # BOM 中没有这位号 → 已被第一步清空，最终保持空（以 BOM 为准）
            row['after_comment'] = ''
            row['write_status'] = '清空'
            row['reason'] = 'BOM 中无此位号参数，已清空'
            result.warnings.append(f"位号 {designator}: BOM 中无参数，已清空")
            audit_rows.append(row)
            continue

        entries_list = cd_map.get(designator) or []
        if not entries_list:
            # PCB 中无法在 WS 流定位到位号的 prev（cd_map 缺失）
            row['write_status'] = '失败'
            row['reason'] = 'PCB 中找不到此位号的 Comment 写入位置'
            result.warnings.append(
                f"位号 {designator} 在 PCB WideStrings6 中找不到 prev 配对，跳过"
            )
            audit_rows.append(row)
            continue

        success = _set_comment(raw_data, ws_offset, designator, new_comment,
                               list(pcb_comps_by_des.keys()), _ws_total_size)
        if success:
            result.success_count += 1
            row['write_status'] = '成功'
            row['reason'] = ''
        else:
            # 写入失败：Comment 已被第一步清空但新值没写进去，实际是空
            row['write_status'] = '失败'
            row['after_comment'] = ''
            cap_chars = (entries_list[0]['comment_entry'].strlen - 2) // 2
            row['reason'] = f'新值 {len(new_comment)} 字符超过原 Comment 容量 {cap_chars} 字符，无法原地写入'
            result.failed_designators.append(designator)
            result.warnings.append(
                f"位号 {designator} 的新参数 '{new_comment}' 超出原 Comment 空间，跳过"
            )
        audit_rows.append(row)

    result.audit_rows = audit_rows

    # 写入新文件
    with open(output_path, 'wb') as f:
        f.write(raw_data)

    return result

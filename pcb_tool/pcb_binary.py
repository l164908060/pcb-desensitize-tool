"""
PcbDoc 二进制解析与修改模块

Altium Designer PcbDoc 是 OLE2 复合文档格式。
本模块直接读取/修改 WideStrings6 流（包含元件 Comment 和 Designator 字符串），
保持流大小不变，仅替换字符串内容，OLE 目录和 FAT 结构不动。
"""

import struct
import olefile
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class WsEntry:
    """WideStrings6 流中的一条字符串记录"""
    ws_index: int          # 在 ws_entries 列表中的位置索引
    raw_index: int         # 文件中存储的 index 字段值
    strlen: int            # 字符串字节长度（含 UTF-16LE null 终止符）
    text: str              # 解析出的字符串内容
    file_offset: int       # 在 PcbDoc 文件中的字节偏移


def parse_widestrings(ws_data: bytes) -> List[WsEntry]:
    """
    解析 WideStrings6 流数据
    格式：[4字节 index][4字节 strlen（含null）][UTF-16LE 字符串+null]
    """
    entries = []
    offset = 0
    while offset < len(ws_data):
        if offset + 8 > len(ws_data):
            break
        raw_index = struct.unpack_from('<I', ws_data, offset)[0]
        strlen = struct.unpack_from('<I', ws_data, offset + 4)[0]
        if strlen > 4096 or strlen < 2:
            break
        try:
            s_bytes = ws_data[offset + 8: offset + 8 + strlen]
            text = s_bytes.decode('utf-16-le', errors='replace').rstrip('\x00')
        except Exception:
            break
        entries.append(WsEntry(
            ws_index=len(entries),
            raw_index=raw_index,
            strlen=strlen,
            text=text,
            file_offset=offset,
        ))
        offset += 8 + strlen
    return entries


def find_widestrings_offset(raw_file: bytes) -> Tuple[int, int]:
    """
    在原始 PcbDoc 文件字节中定位 WideStrings6 数据的起始偏移和逻辑大小

    Altium PcbDoc 是 OLE2 复合文档。WideStrings6 流根据大小有两种存放方式：
    - 普通 FAT 流（>= minisectorcutoff，默认 4096 字节）：起始扇区直接通过 FAT 链索引
    - mini-FAT 流（< minisectorcutoff）：内容存放在 Root Entry 的 mini-stream 容器里，
                                        通过 mini-FAT 索引（小流，节省空间）

    本函数通过 olefile 读取 WideStrings6 的内容（用于构造 magic），再用 olefile 的
    direntry.size 字段获取流的逻辑大小（避免 mini-stream 跨扇区误读），然后用
    magic 在原始字节中搜索定位物理偏移，同时兼容两种存放方式。

    返回:
        (ws_offset, ws_size) - WideStrings6 数据的物理偏移和逻辑大小（字节）
    """
    # 将文件写入临时位置以供 olefile 读取
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.PcbDoc', delete=False) as tmp:
        tmp.write(raw_file)
        tmp_path = tmp.name

    try:
        ole = olefile.OleFileIO(tmp_path)
        try:
            # 读目录条目，拿到流的逻辑大小（避免 mini-stream 跨扇区误读）
            entry = ole._find(['WideStrings6', 'Data'])
            if entry is None:
                raise ValueError("无法在 PcbDoc 中找到 WideStrings6/Data 流")
            dir_entry = ole.direntries[entry] if isinstance(entry, int) else entry
            ws_size = dir_entry.size

            # 读数据用于构造 magic
            ws_data = ole.openstream('WideStrings6/Data').read()
        finally:
            ole.close()
    finally:
        os.unlink(tmp_path)

    if len(ws_data) < 8:
        raise ValueError("WideStrings6 流过短，无法定位")

    # 用 ws_data 头部构造 magic 在 raw_file 中搜索物理偏移
    if len(ws_data) >= 32:
        magic = ws_data[:32]
    else:
        magic = ws_data

    pos = raw_file.find(magic)
    if pos < 0:
        magic16 = ws_data[:16] if len(ws_data) >= 16 else ws_data
        pos = raw_file.find(magic16)
    if pos < 0:
        magic8 = ws_data[:8]
        pos = raw_file.find(magic8)

    if pos < 0:
        raise ValueError(
            f"无法在 PcbDoc 文件中定位 WideStrings6 数据（流长 {ws_size}）"
        )

    return pos, ws_size


def parse_components(comp_data: bytes) -> List[dict]:
    """
    解析 Components6 流数据，返回元件属性字典列表
    每条记录格式：[4字节 record_len][pipe分隔的key=value|key=value|...][null]

    注意：Altium 简体中文版的 PATTERN/Comment 等值字段是 GBK 编码
    （纯 ASCII 内容不受影响；中文封装名如 "插件"、"带散热" 会被正确还原）
    """
    components = []
    offset = 0
    while offset < len(comp_data):
        if offset + 4 > len(comp_data):
            break
        rec_len = struct.unpack_from('<I', comp_data, offset)[0]
        offset += 4
        rec_data = comp_data[offset:offset + rec_len]
        null_pos = rec_data.find(b'\x00')
        text_bytes = rec_data[:null_pos] if null_pos >= 0 else rec_data

        # 整体用 GBK 解码，兼容 ASCII 键名
        text = text_bytes.decode('gbk', errors='replace')

        props = {}
        for part in text.split('|'):
            if '=' in part:
                k, v = part.split('=', 1)
                props[k] = v
        components.append(props)
        offset += rec_len
    return components


def build_comment_designator_map(ws_entries: List[WsEntry], designators: Optional[List[str]] = None) -> dict:
    """
    从 WideStrings6 解析出 Designator → Comment 映射

    不依赖"奇偶位"硬假设。规则：
    - WideStrings6 中存在两类布局：
        布局A（旧文件，无 PCB 全局注释）：从 idx 0 开始严格 (Comment, Des) 交替
        布局B（新文件，有 PCB 全局注释）：idx 0 是 PCB 全局注释，
                之后从 idx 1 开始 (Comment, Des) 交替，但 Comment 在奇数位、Des 在偶数位
                之后可能混入尺寸/网络名字符串
    - 两种布局都满足：对每个 Designator 字符串，Comment 一定是它的"前一条"条目
    - 用 Components6 的 SOURCEDESIGNATOR 作为权威 designator 集合，反查 WideStrings6

    重要：同一位号字符串可能在 WS 流中出现多次（Altium 在元件描述/网络组等位置
    复用位号文本）。这里用 list 收集该位号所有出现位置的 prev 候选，
    避免后续 dict 覆盖导致"前面真正的 Comment 被漏清"
    """
    # 已知位号集合（小写匹配不区分大小写，原始 PcbDoc 中位号大小写不敏感）
    des_set = set()
    if designators:
        des_set = {d.strip() for d in designators if d and d.strip()}

    # text -> list[{comment_entry, designator_entry}]
    # 用 list 不 dict，保留同名位号的所有候选（同一文本可能出现多次）
    mapping: Dict[str, List[dict]] = {}
    for e in ws_entries:
        text = e.text.strip()
        if not text:
            continue
        # 是否是已知位号？
        if des_set and text not in des_set:
            continue
        # 在 ws_entries 中的位置
        idx_in_list = ws_entries.index(e)
        if idx_in_list == 0:
            continue  # 第一条没有"前一条"，是 PCB 全局注释
        prev = ws_entries[idx_in_list - 1]
        # 防呆：前一条不能也是已知位号（避免误判配对方向）
        if des_set and prev.text.strip() in des_set:
            continue
        # 防呆：前一条不能是尺寸/网络名等明显非 Comment 的内容
        # 这里不强加判断，万一未来有特殊命名
        mapping.setdefault(text, []).append({
            'comment_entry': prev,
            'designator_entry': e,
        })
    return mapping


def clear_all_comments(raw_file: bytearray, ws_offset: int, ws_total_size: int,
                      designators: Optional[List[str]] = None) -> Tuple[bytearray, int]:
    """
    清除所有 Comment 字符串（保持文件大小不变）

    参数:
        raw_file: 文件字节数组（会被原地修改）
        ws_offset: WideStrings6 数据在文件中的起始偏移
        ws_total_size: WideStrings6 数据的总大小
        designators: 元件位号列表（来自 Components6 的 SOURCEDESIGNATOR）
                     传入后可正确识别 Comment 而不依赖布局
    返回:
        (修改后的字节数组, 清除的 Comment 数量)
    """
    ws_data = bytes(raw_file[ws_offset:ws_offset + ws_total_size])
    entries = parse_widestrings(ws_data)
    cd_map = build_comment_designator_map(entries, designators)

    cleared_count = 0
    # cd_map 现在是 {text: list[entry]}——同名位号有多个 prev 候选，全部清空
    for _des, entries_list in cd_map.items():
        for m in entries_list:
            comment_entry = m['comment_entry']
            # 用 UTF-16LE null 填充整个 strlen 区域（保持长度不变）
            string_start = ws_offset + comment_entry.file_offset + 8
            for i in range(comment_entry.strlen):
                raw_file[string_start + i] = 0x00
            cleared_count += 1

    return raw_file, cleared_count


def set_comment(raw_file: bytearray, ws_offset: int, designator: str, new_comment: str,
                designators: Optional[List[str]] = None,
                ws_total_size: Optional[int] = None) -> bool:
    """
    修改指定位号的 Comment 字符串
    如果新值比原值短，剩余空间用 null 填充；新值不能比原值长（返回 False）

    参数:
        raw_file: 文件字节数组
        ws_offset: WideStrings6 数据起始偏移
        designator: 目标位号
        new_comment: 新 Comment 值
        designators: 元件位号列表（用于 build_comment_designator_map 反查）
        ws_total_size: WideStrings6 数据总大小（不传则读到文件尾，避免硬编码截断大文件）
    返回:
        True 表示成功，False 表示失败（找不到位号或新值过长）
    """
    if ws_total_size is None:
        ws_total_size = len(raw_file) - ws_offset
    ws_data = bytes(raw_file[ws_offset:ws_offset + ws_total_size])
    entries = parse_widestrings(ws_data)
    cd_map = build_comment_designator_map(entries, designators)

    new_bytes = new_comment.encode('utf-16-le') + b'\x00\x00'  # UTF-16LE + null
    # 取同名位号第一个匹配（即元件真正 Comment 区域，通常第一次出现就是元件位置）
    entries_list = cd_map.get(designator.strip()) or []
    if not entries_list:
        return False
    comment_entry = entries_list[0]['comment_entry']
    max_bytes = comment_entry.strlen
    if len(new_bytes) > max_bytes:
        return False  # 新值过长，无法原地修改

    string_start = ws_offset + comment_entry.file_offset + 8
    for j in range(max_bytes):
        if j < len(new_bytes):
            raw_file[string_start + j] = new_bytes[j]
        else:
            # 剩余空间用 UTF-16LE null 填充（0x00）
            # 注意：不能用单字节 0x20 填充——两个连续 0x20 会被 UTF-16LE
            # 解码成 U+2020 '†'，导致 Comment 尾部出现乱码
            raw_file[string_start + j] = 0x00
    return True


def get_pcb_info(pcb_path: str) -> dict:
    """获取 PcbDoc 文件信息：位号列表、Comment 映射等"""
    ole = olefile.OleFileIO(pcb_path)
    try:
        ws_data = ole.openstream('WideStrings6/Data').read()
        comp_data = ole.openstream('Components6/Data').read()
    finally:
        ole.close()

    ws_entries = parse_widestrings(ws_data)
    components = parse_components(comp_data)
    # 用 Components6 的位号作为权威，反查 WideStrings6 的 Comment
    all_designators = [c.get('SOURCEDESIGNATOR', '').strip() for c in components]
    cd_map = build_comment_designator_map(ws_entries, all_designators)

    # 合并：元件定义 + Comment 映射
    result = []
    for comp in components:
        des = comp.get('SOURCEDESIGNATOR', '').strip()
        if not des:
            continue
        # cd_map 现在是 {text: list}；取同名位号第一个匹配作为"当前 Comment"显示
        entries_list = cd_map.get(des) or []
        if entries_list:
            result.append({
                'designator': des,
                'current_comment': entries_list[0]['comment_entry'].text,
                'pattern': comp.get('PATTERN', ''),
            })
        else:
            # 在 WS 中找不到的元件，从 SOURCELIBREFERENCE 推断
            lib_ref = comp.get('SOURCELIBREFERENCE', '')
            result.append({
                'designator': des,
                'current_comment': lib_ref,
                'pattern': comp.get('PATTERN', ''),
            })

    return {
        'component_count': len(components),
        'ws_entry_count': len(ws_entries),
        'components': result,
    }

// PCB 工具前端逻辑

(function() {
    'use strict';

    const state = {
        currentMode: 'desensitize',
        pcbFile: null,        // File 对象
        bomFile: null,        // File 对象
        previewData: null,    // 预览数据
    };

    // DOM 工具
    const $ = (sel) => document.querySelector(sel);
    const $$ = (sel) => document.querySelectorAll(sel);

    // 初始化
    document.addEventListener('DOMContentLoaded', init);

    function init() {
        setupModeSwitcher();
        setupFileInputs('desensitize', 'pcb');
        setupFileInputs('fill', 'pcb');
        setupBomInput();
        setupDropZones();
        setupActionButtons();
        setupPreviewToggle();
    }

    // =================== 模式切换 ===================
    function setupModeSwitcher() {
        $$('.mode-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const mode = btn.dataset.mode;
                switchMode(mode);
            });
        });
    }

    function switchMode(mode) {
        state.currentMode = mode;
        $$('.mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === mode));
        $$('.panel').forEach(p => p.style.display = 'none');
        $(`#panel-${mode}`).style.display = 'block';
    }

    // =================== 文件输入 ===================
    function setupFileInputs(panelId, type) {
        const inputId = panelId === 'desensitize' ? 'file-pcb-desensitize' : 'file-pcb-fill';
        const fileInput = $(`#${inputId}`);
        if (!fileInput) return;

        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                onPcbSelected(file, panelId);
            }
        });
    }

    function setupBomInput() {
        const fileInput = $('#file-bom');
        if (!fileInput) return;
        fileInput.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                onBomSelected(file);
            }
        });
    }

    function setupDropZones() {
        const drops = [
            { id: 'drop-desensitize', handler: 'desensitize' },
            { id: 'drop-pcb-fill', handler: 'fill-pcb' },
            { id: 'drop-bom', handler: 'fill-bom' },
        ];

        drops.forEach(d => {
            const el = $(`#${d.id}`);
            if (!el) return;

            el.addEventListener('dragover', (e) => {
                e.preventDefault();
                el.classList.add('dragover');
            });
            el.addEventListener('dragleave', () => {
                el.classList.remove('dragover');
            });
            el.addEventListener('drop', (e) => {
                e.preventDefault();
                el.classList.remove('dragover');
                const file = e.dataTransfer.files[0];
                if (file) {
                    if (d.handler === 'desensitize' || d.handler === 'fill-pcb') {
                        onPcbSelected(file, d.handler === 'desensitize' ? 'desensitize' : 'fill');
                    } else if (d.handler === 'fill-bom') {
                        onBomSelected(file);
                    }
                }
            });
        });
    }

    // =================== 文件选择回调 ===================
    function onPcbSelected(file, panelId) {
        if (!file.name.toLowerCase().endsWith('.pcbdoc')) {
            showError('请选择 .PcbDoc 格式的文件');
            return;
        }
        state.pcbFile = file;
        // 脱敏面板用 #filename-desensitize；回填面板的 PCB/BOM 摘要区
        // 共享 #files-summary-fill，PCB 的文件名 span id 是 #filename-pcb-fill
        let filenameSel = `#filename-${panelId}`;
        if (panelId === 'fill') {
            filenameSel = '#filename-pcb-fill';
        }
        const filenameEl = $(filenameSel);
        const selectedEl = $(`#selected-${panelId}`);
        if (filenameEl) filenameEl.textContent = file.name;
        if (selectedEl) selectedEl.style.display = 'flex';

        if (panelId === 'desensitize') {
            previewPcb(file);
        } else if (panelId === 'fill') {
            // 回填面板的"PCB 已选"摘要区域默认隐藏，这里选中后显示
            const summaryFill = $('#files-summary-fill');
            if (summaryFill) summaryFill.style.display = 'block';
            updateFillButton();
        }
    }

    function onBomSelected(file) {
        const ext = file.name.toLowerCase();
        if (!ext.endsWith('.xls') && !ext.endsWith('.xlsx')) {
            showError('请选择 .xls 或 .xlsx 格式的 BOM 文件');
            return;
        }
        state.bomFile = file;
        $('#filename-bom').textContent = file.name;
        $('#files-summary-fill').style.display = 'block';
        updateFillButton();
    }

    function clearFile(type) {
        if (type === 'desensitize') {
            state.pcbFile = null;
            $('#file-pcb-desensitize').value = '';
            $('#selected-desensitize').style.display = 'none';
            $('#preview-desensitize').style.display = 'none';
            $('#btn-desensitize').disabled = true;
        } else if (type === 'pcb-fill') {
            state.pcbFile = null;
            $('#file-pcb-fill').value = '';
            updateFillButton();
        } else if (type === 'bom') {
            state.bomFile = null;
            $('#file-bom').value = '';
            $('#files-summary-fill').style.display = 'none';
            updateFillButton();
        }
    }

    // 绑定清除按钮
    document.addEventListener('click', (e) => {
        if (e.target.classList.contains('btn-clear-file')) {
            const target = e.target.dataset.target;
            if (target === 'desensitize') clearFile('desensitize');
            else if (target === 'pcb-fill') clearFile('pcb-fill');
            else if (target === 'bom') clearFile('bom');
        }
    });

    // =================== 预览 ===================
    async function previewPcb(file) {
        showLoading('解析 PCB 文件...');
        try {
            const formData = new FormData();
            formData.append('pcb_file', file);

            const response = await fetch('/api/preview', { method: 'POST', body: formData });
            const data = await response.json();

            if (!data.success) {
                showError(data.error);
                return;
            }

            state.previewData = data;
            state.savedFilename = data.saved_filename;

            $('#preview-count').textContent = data.component_count;
            $('#preview-desensitize').style.display = 'block';
            $('#btn-desensitize').disabled = false;

            // 填充预览列表
            const tbody = $('#preview-tbody');
            tbody.innerHTML = '';
            data.components.forEach(c => {
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td>${escapeHtml(c.designator)}</td>
                    <td>${escapeHtml(c.current_comment || '(空)')}</td>
                    <td>${escapeHtml(c.pattern || '')}</td>
                `;
                tbody.appendChild(tr);
            });
        } catch (e) {
            showError('预览失败: ' + e.message);
        } finally {
            hideLoading();
        }
    }

    // =================== 操作按钮 ===================
    function setupActionButtons() {
        $('#btn-desensitize').addEventListener('click', executeDesensitize);
        $('#btn-fill').addEventListener('click', executeFill);
    }

    function setupPreviewToggle() {
        $('#toggle-list').addEventListener('click', () => {
            const list = $('#preview-list');
            const toggle = $('#toggle-list');
            if (list.style.display === 'none') {
                list.style.display = 'block';
                toggle.textContent = '收起 ▲';
            } else {
                list.style.display = 'none';
                toggle.textContent = '查看详情 ▼';
            }
        });
    }

    async function executeDesensitize() {
        if (!state.savedFilename) {
            showError('请先上传 PCB 文件');
            return;
        }

        showLoading('正在清除 Comment...');
        try {
            const response = await fetch('/api/desensitize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ saved_filename: state.savedFilename }),
            });
            const data = await response.json();

            if (!data.success) {
                showError(data.error);
                return;
            }

            $('#result-msg-desensitize').textContent = data.message;
            setupDownloadButton('#download-desensitize', data.output_filename);
            $('#result-desensitize').style.display = 'block';
        } catch (e) {
            showError('脱敏失败: ' + e.message);
        } finally {
            hideLoading();
        }
    }

    async function executeFill() {
        if (!state.pcbFile || !state.bomFile) {
            showError('请同时上传 PCB 和 BOM 文件');
            return;
        }

        showLoading('正在从 BOM 写入 Comment...');
        try {
            const formData = new FormData();
            formData.append('pcb_file', state.pcbFile);
            formData.append('bom_file', state.bomFile);

            const response = await fetch('/api/fill', { method: 'POST', body: formData });
            const data = await response.json();

            if (!data.success) {
                showError(data.error);
                return;
            }

            $('#result-msg-fill').textContent = data.message;
            setupDownloadButton('#download-fill', data.output_filename);
            $('#result-fill').style.display = 'block';

            // 显示警告详情
            const detailsEl = $('#result-details-fill');
            const warningsEl = $('#result-warnings');
            if (data.warnings && data.warnings.length > 0) {
                detailsEl.style.display = 'block';
                warningsEl.innerHTML = data.warnings.map(w => `<div>⚠ ${escapeHtml(w)}</div>`).join('');
            } else {
                detailsEl.style.display = 'none';
            }

            // 渲染回填校验报告
            renderAuditTable(data.audit_rows || []);
        } catch (e) {
            showError('回填失败: ' + e.message);
        } finally {
            hideLoading();
        }
    }

    function updateFillButton() {
        $('#btn-fill').disabled = !(state.pcbFile && state.bomFile);
    }

    // =================== 下载（fetch + Blob，绕开 360 对 Content-Disposition 的怪解析） ===================
    /**
     * 把下载按钮由 <a href> + download 属性切换为 JS 主动 fetch+Blob 下载
     * 参数:
     *   selector: 下载按钮的 CSS 选择器
     *   filename: 接口返回的输出文件名
     * 返回:
     *   无
     * 说明:
     *   360 浏览器对带中文文件名 + 双字段 Content-Disposition 解析异常，导致
     *   "无法从网站上提取文件"。改用 Blob 触发下载，完全由前端 JS 主导。
     */
    function setupDownloadButton(selector, filename) {
        const btn = $(selector);
        if (!btn) return;
        const href = `/api/download/${filename}`;
        btn.dataset.href = href;
        btn.dataset.filename = filename;
        // 用 onclick 赋值确保多次调用时只保留最新一次处理逻辑，不重复绑定
        btn.onclick = (e) => {
            e.preventDefault();
            downloadViaBlob(href, filename, btn);
        };
    }

    /**
     * 下载文件：以 fetch 拉取二进制，再用 Blob + objectURL 触发浏览器下载
     * 参数:
     *   href: 服务端下载地址
     *   filename: 保存到本地的文件名
     *   btn: 触发本次下载的按钮，用于在下载过程中显示状态
     * 返回:
     *   无（异步）；异常时弹错误吐司
     */
    async function downloadViaBlob(href, filename, btn) {
        if (btn.dataset.busy === '1') return;
        btn.dataset.busy = '1';
        const origText = btn.textContent;
        btn.textContent = '⏳ 下载中...';
        try {
            const resp = await fetch(href);
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const blob = await resp.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = filename;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        } catch (err) {
            showError('下载失败: ' + err.message);
        } finally {
            btn.textContent = origText;
            delete btn.dataset.busy;
        }
    }

    // =================== 回填校验报告（HTML 表格预览） ===================
    /**
     * 渲染回填校验报告到页面的 HTML 表格
     * 参数:
     *   rows: 后端返回的 audit 列表，每条包含 designator/pattern/bom_value/
     *         before_comment/after_comment/bom_status/write_status/reason
     * 返回:
     *   无
     * 说明:
     *   按状态着色：成功=绿、跳过=黄、失败=红、BOM缺失=橙；
     *   改前/改后相同的不算改动，便于核对改了哪些位号。
     */
    function renderAuditTable(rows) {
        const section = $('#audit-section-fill');
        const tbody = $('#audit-tbody');
        const summary = $('#audit-summary');
        if (!section || !tbody) return;

        if (!rows || rows.length === 0) {
            section.style.display = 'none';
            return;
        }
        section.style.display = 'block';

        // 统计
        const counts = { 成功: 0, 跳过: 0, 失败: 0, 匹配: 0, 缺失: 0 };
        let changedCount = 0;
        for (const r of rows) {
            counts[r.write_status] = (counts[r.write_status] || 0) + 1;
            counts[r.bom_status] = (counts[r.bom_status] || 0) + 1;
            if (r.write_status === '成功' && (r.before_comment || '') !== (r.after_comment || '')) {
                changedCount += 1;
            }
        }
        summary.innerHTML = `共 <b>${rows.length}</b> 个位号，`
            + `<b class="audit-tag audit-tag-success">成功 ${counts['成功'] || 0}</b>，`
            + `<b class="audit-tag audit-tag-skip">跳过 ${counts['跳过'] || 0}</b>，`
            + `<b class="audit-tag audit-tag-fail">失败 ${counts['失败'] || 0}</b>，`
            + `<b class="audit-tag audit-tag-miss">BOM 缺失 ${counts['缺失'] || 0}</b>`
            + `，<b>实际改动 ${changedCount}</b> 条`;

        // 渲染表格行
        tbody.innerHTML = '';
        for (const r of rows) {
            const tr = document.createElement('tr');
            // 改前/改后相同的情况，在 after 加 (未变) 提示
            const changed = (r.before_comment || '') !== (r.after_comment || '');
            tr.className = `audit-row ${statusToRowClass(r.bom_status, r.write_status)}`;
            tr.innerHTML = `
                <td><code>${escapeHtml(r.designator)}</code></td>
                <td>${escapeHtml(r.pattern || '')}</td>
                <td>${escapeHtml(r.bom_value || '')}</td>
                <td class="audit-comment">${escapeHtml(r.before_comment || '')}</td>
                <td class="audit-comment">${escapeHtml(r.after_comment || '')}${changed ? '' : ' <span class="audit-unchanged">(未变)</span>'}</td>
                <td><span class="${statusToTagClass(r.bom_status)}">${escapeHtml(r.bom_status)}</span></td>
                <td><span class="${statusToTagClass(r.write_status)}">${escapeHtml(r.write_status)}</span></td>
                <td class="audit-reason">${escapeHtml(r.reason || '')}</td>
            `;
            tbody.appendChild(tr);
        }
    }

    /**
     * 把审计行的"组合状态"映射到行的 CSS 类（用于整体着色）
     */
    function statusToRowClass(bomStatus, writeStatus) {
        if (writeStatus === '失败') return 'audit-row-fail';
        if (writeStatus === '成功') return 'audit-row-success';
        if (bomStatus === '缺失') return 'audit-row-miss';
        return 'audit-row-skip';
    }

    /**
     * 把状态字符串映射到 .audit-tag-* 样式类
     */
    function statusToTagClass(status) {
        const map = {
            '成功': 'audit-tag audit-tag-success',
            '跳过': 'audit-tag audit-tag-skip',
            '失败': 'audit-tag audit-tag-fail',
            '匹配': 'audit-tag audit-tag-bommatch',
            '缺失': 'audit-tag audit-tag-miss',
        };
        return map[status] || 'audit-tag audit-tag-neutral';
    }

    // =================== 工具函数 ===================
    function showLoading(text) {
        $('#loading-text').textContent = text || '处理中...';
        $('#loading').style.display = 'flex';
    }

    function hideLoading() {
        $('#loading').style.display = 'none';
    }

    function showError(msg) {
        const toast = document.createElement('div');
        toast.className = 'error-toast';
        toast.textContent = '❌ ' + msg;
        document.body.appendChild(toast);
        setTimeout(() => toast.remove(), 5000);
    }

    function escapeHtml(s) {
        if (s == null) return '';
        return String(s)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }
})();

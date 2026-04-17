// Video Transcriber Web界面交互脚本

class VideoTranscriberUI {
    constructor() {
        this.apiBaseUrl = window.location.origin;
        this.wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/transcribe`;
        this.ws = null;
        this.currentTaskId = null;
        this.batchTasks = new Map();
        this.history = this.loadHistory();
        this.selectedFile = null;
        this.selectedBatchFiles = [];
        this.themeStorageKey = 'video_transcriber_theme';
        this.currentTheme = 'light';
        this.statusPollingTimer = null;
        this.logPollingTimer = null;
        this.logsAutoScroll = true;
        this.logsPaused = false;
        this.logFilters = {
            level: 'all',
            keyword: ''
        };
        this.currentLogLines = [];

        this.init();
    }

    init() {
        this.applySavedTheme();
        this.bindEvents();
        this.loadHistory();
        this.displayHistory();
        this.initTabAnimation();
        this.initRealtimeStatusCards();
        this.startStatusPolling();
        this.initLogStream();
        this.initWebSocket();
    }

    bindEvents() {
        // 单个转录 - 文件选择
        const videoFileInput = document.getElementById('videoFile');
        const uploadArea = document.getElementById('uploadArea');

        // 点击上传区域
        uploadArea.addEventListener('click', (e) => {
            if (e.target !== videoFileInput) {
                videoFileInput.click();
            }
        });

        // 文件选择变化
        videoFileInput.addEventListener('change', (e) => {
            this.handleFileSelect(e.target.files[0]);
        });

        // 拖拽上传
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('drag-over');
        });

        uploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('drag-over');
            const file = e.dataTransfer.files[0];
            if (file && (file.type.startsWith('video/') || file.type.startsWith('audio/'))) {
                videoFileInput.files = e.dataTransfer.files;
                this.handleFileSelect(file);
            } else {
                this.showToast('请上传视频或音频文件', 'warning');
            }
        });

        // 移除文件
        document.getElementById('removeFileBtn').addEventListener('click', (e) => {
            e.stopPropagation();
            this.removeSelectedFile();
        });

        // 转录按钮
        document.getElementById('transcribeBtn').addEventListener('click', () => {
            this.handleSingleTranscribe();
        });

        // 首屏快捷转录按钮
        const transcribeQuickBtn = document.getElementById('transcribeQuickBtn');
        if (transcribeQuickBtn) {
            transcribeQuickBtn.addEventListener('click', () => {
                this.handleSingleTranscribe();
            });
        }

        // 批量转录 - 文件选择
        const batchFilesInput = document.getElementById('batchFiles');
        const batchUploadArea = document.getElementById('batchUploadArea');

        batchUploadArea.addEventListener('click', (e) => {
            if (e.target !== batchFilesInput) {
                batchFilesInput.click();
            }
        });

        batchFilesInput.addEventListener('change', (e) => {
            this.handleBatchFilesSelect(e.target.files);
        });

        batchUploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            batchUploadArea.classList.add('drag-over');
        });

        batchUploadArea.addEventListener('dragleave', (e) => {
            e.preventDefault();
            batchUploadArea.classList.remove('drag-over');
        });

        batchUploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            batchUploadArea.classList.remove('drag-over');
            const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('video/') || f.type.startsWith('audio/'));
            if (files.length > 0) {
                batchFilesInput.files = e.dataTransfer.files;
                this.handleBatchFilesSelect(files);
            } else {
                this.showToast('请上传视频或音频文件', 'warning');
            }
        });

        // 批量转录按钮
        document.getElementById('batchTranscribeBtn').addEventListener('click', () => {
            this.handleBatchTranscribe();
        });

        // 复制结果按钮
        document.getElementById('copyBtn').addEventListener('click', () => {
            this.copyResult();
        });

        // 下载结果按钮
        document.getElementById('downloadBtn').addEventListener('click', () => {
            this.downloadResult();
        });

        // 清空结果按钮
        document.getElementById('clearResultBtn').addEventListener('click', () => {
            this.clearResult();
        });

        // 清空历史按钮
        document.getElementById('clearHistoryBtn').addEventListener('click', () => {
            this.clearHistory();
        });

        // 输出格式改变事件
        document.getElementById('outputFormat').addEventListener('change', (e) => {
            const timestamps = document.getElementById('timestamps');
            timestamps.disabled = e.target.value === 'txt';
            if (e.target.value === 'txt') {
                timestamps.checked = false;
            }
        });

        // 主题切换
        const themeToggleBtn = document.getElementById('themeToggleBtn');
        if (themeToggleBtn) {
            themeToggleBtn.addEventListener('click', () => this.toggleTheme());
        }

        // 日志刷新
        const refreshLogsBtn = document.getElementById('refreshLogsBtn');
        if (refreshLogsBtn) {
            refreshLogsBtn.addEventListener('click', () => {
                this.fetchLogStream();
            });
        }

        const logLevelFilter = document.getElementById('logLevelFilter');
        if (logLevelFilter) {
            logLevelFilter.addEventListener('change', (event) => {
                this.logFilters.level = event.target.value;
                this.fetchLogStream();
            });
        }

        const logKeywordInput = document.getElementById('logKeywordInput');
        if (logKeywordInput) {
            logKeywordInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') {
                    this.logFilters.keyword = event.target.value.trim();
                    this.fetchLogStream();
                }
            });

            logKeywordInput.addEventListener('blur', (event) => {
                const newKeyword = event.target.value.trim();
                if (newKeyword !== this.logFilters.keyword) {
                    this.logFilters.keyword = newKeyword;
                    this.fetchLogStream();
                }
            });
        }

        const pauseLogsBtn = document.getElementById('pauseLogsBtn');
        if (pauseLogsBtn) {
            pauseLogsBtn.addEventListener('click', () => {
                this.toggleLogsPause();
            });
        }

        const exportLogsBtn = document.getElementById('exportLogsBtn');
        if (exportLogsBtn) {
            exportLogsBtn.addEventListener('click', () => {
                this.exportCurrentLogs();
            });
        }

        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.setLogIndicator('paused', '页面后台，已降低刷新频率');
            } else {
                if (!this.logsPaused) {
                    this.setLogIndicator('live', '实时更新');
                }
                this.fetchLogStream();
                this.fetchRealtimeStatus();
            }
        });
    }

    applySavedTheme() {
        const savedTheme = localStorage.getItem(this.themeStorageKey);
        const defaultDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
        const theme = savedTheme || (defaultDark ? 'dark' : 'light');
        this.applyTheme(theme);
    }

    applyTheme(theme) {
        const root = document.documentElement;
        const toggleText = document.getElementById('themeToggleText');
        const toggleBtn = document.getElementById('themeToggleBtn');

        this.currentTheme = theme;
        root.setAttribute('data-theme', theme);
        localStorage.setItem(this.themeStorageKey, theme);

        if (toggleText) {
            toggleText.textContent = theme === 'dark' ? '浅色' : '深色';
        }

        if (toggleBtn) {
            toggleBtn.innerHTML = theme === 'dark'
                ? '<i class="bi bi-sun me-1"></i><span id="themeToggleText">浅色</span>'
                : '<i class="bi bi-moon-stars me-1"></i><span id="themeToggleText">深色</span>';
        }
    }

    toggleTheme() {
        const nextTheme = this.currentTheme === 'dark' ? 'light' : 'dark';
        this.applyTheme(nextTheme);
        this.showToast(`已切换到${nextTheme === 'dark' ? '深色' : '浅色'}主题`, 'info');
    }

    initTabAnimation() {
        const tabButtons = document.querySelectorAll('[data-bs-toggle="tab"]');
        tabButtons.forEach((tabButton) => {
            tabButton.addEventListener('shown.bs.tab', (event) => {
                const targetSelector = event.target.getAttribute('data-bs-target');
                this.animateTabPane(targetSelector);
                this.updateQuickBarVisibility(targetSelector);
            });
        });

        this.updateQuickBarVisibility('#single');
    }

    animateTabPane(targetSelector) {
        const pane = document.querySelector(targetSelector);
        if (!pane) return;

        pane.classList.remove('tab-enter');
        void pane.offsetWidth;
        pane.classList.add('tab-enter');
    }

    updateQuickBarVisibility(targetSelector) {
        // Bar is now controlled by file-selection state, not tab.
        // When switching away from #single, always hide; when returning,
        // restore based on whether a file is selected.
        const quickBar = document.getElementById('quickTranscribeBar');
        if (!quickBar) return;

        if (targetSelector !== '#single') {
            quickBar.classList.remove('visible');
        } else if (this.selectedFile) {
            quickBar.classList.add('visible');
        }
    }

    showFileStatusBar(file) {
        const quickBar = document.getElementById('quickTranscribeBar');
        const nameEl = document.getElementById('quickBarFileName');
        const sizeEl = document.getElementById('quickBarFileSize');
        if (!quickBar) return;

        if (nameEl) nameEl.textContent = file.name;
        if (sizeEl) sizeEl.textContent = this.formatFileSize(file.size);

        // Trigger re-animation
        quickBar.classList.remove('visible');
        void quickBar.offsetWidth;
        quickBar.classList.add('visible');
    }

    hideFileStatusBar() {
        const quickBar = document.getElementById('quickTranscribeBar');
        if (quickBar) quickBar.classList.remove('visible');
    }

    async initRealtimeStatusCards() {
        await this.fetchRealtimeStatus();
    }

    startStatusPolling() {
        if (this.statusPollingTimer) {
            clearInterval(this.statusPollingTimer);
        }

        this.statusPollingTimer = setInterval(() => {
            this.fetchRealtimeStatus();
        }, 15000);
    }

    async fetchRealtimeStatus() {
        try {
            const [infoRes, healthRes, statsRes] = await Promise.allSettled([
                fetch(`${this.apiBaseUrl}/info`),
                fetch(`${this.apiBaseUrl}/health`),
                fetch(`${this.apiBaseUrl}/api/v1/transcribe/stats`)
            ]);

            let modelStatus = '未知';
            let gpuStatus = '未知';
            let recentTasks = '0';

            if (infoRes.status === 'fulfilled' && infoRes.value.ok) {
                const infoData = await infoRes.value.json();
                const modelName = infoData.models?.default || 'sensevoice-small';
                modelStatus = `${modelName} / 就绪`;
                gpuStatus = infoData.features?.gpu_support ? '可用' : '未启用';
            }

            if (healthRes.status === 'fulfilled' && healthRes.value.ok) {
                const healthData = await healthRes.value.json();
                const ffmpegHealthy = healthData.components?.ffmpeg?.healthy;
                if (!ffmpegHealthy) {
                    modelStatus = `${modelStatus} (依赖降级)`;
                }
            }

            if (statsRes.status === 'fulfilled' && statsRes.value.ok) {
                const statsData = await statsRes.value.json();
                const stats = statsData.data || {};
                const total = Number(stats.total_tasks || stats.total || 0);
                const completed = Number(stats.total_success || stats.completed_tasks || stats.completed || 0);
                recentTasks = `${total} / 已完成 ${completed}`;
            }

            this.updateStatusCards({
                modelStatus,
                gpuStatus,
                recentTasks
            });
        } catch (error) {
            console.error('获取状态卡信息失败:', error);
            this.updateStatusCards({
                modelStatus: '获取失败',
                gpuStatus: '获取失败',
                recentTasks: '获取失败'
            });
        }
    }

    updateStatusCards({ modelStatus, gpuStatus, recentTasks }) {
        const modelEl = document.getElementById('modelStatusValue');
        const gpuEl = document.getElementById('gpuStatusValue');
        const taskEl = document.getElementById('recentTasksValue');

        if (modelEl) modelEl.textContent = modelStatus;
        if (gpuEl) gpuEl.textContent = gpuStatus;
        if (taskEl) taskEl.textContent = recentTasks;
    }

    initLogStream() {
        const logContainer = document.getElementById('logStreamContent');
        if (logContainer) {
            logContainer.addEventListener('scroll', () => {
                const threshold = 24;
                const atBottom = logContainer.scrollTop + logContainer.clientHeight >= logContainer.scrollHeight - threshold;
                this.logsAutoScroll = atBottom;
            });
        }

        this.fetchLogStream();
        this.startLogPolling();
    }

    startLogPolling() {
        if (this.logPollingTimer) {
            clearInterval(this.logPollingTimer);
        }

        this.logPollingTimer = setInterval(() => {
            if (!this.logsPaused) {
                this.fetchLogStream();
            }
        }, 2500);
    }

    toggleLogsPause() {
        this.logsPaused = !this.logsPaused;
        const pauseBtn = document.getElementById('pauseLogsBtn');
        if (pauseBtn) {
            pauseBtn.classList.toggle('btn-outline-warning', !this.logsPaused);
            pauseBtn.classList.toggle('btn-outline-primary', this.logsPaused);
            pauseBtn.innerHTML = this.logsPaused
                ? '<i class="bi bi-play-circle me-1"></i>继续'
                : '<i class="bi bi-pause-circle me-1"></i>暂停';
        }

        if (this.logsPaused) {
            this.setLogIndicator('paused', '已暂停实时刷新');
        } else {
            this.setLogIndicator('live', '实时更新');
            this.fetchLogStream();
        }
    }

    async fetchLogStream() {
        const logContainer = document.getElementById('logStreamContent');
        if (!logContainer) return;

        try {
            const query = new URLSearchParams({
                limit: '120',
                level: this.logFilters.level || 'all',
                keyword: this.logFilters.keyword || ''
            });

            const response = await fetch(`${this.apiBaseUrl}/api/v1/transcribe/logs?${query.toString()}`);
            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(`日志请求失败(${response.status}): ${errorText.slice(0, 120)}`);
            }

            const result = await response.json();
            const lines = result.data?.lines || [];
            this.currentLogLines = lines;

            this.renderLogLines(lines);
            if (!this.logsPaused) {
                this.setLogIndicator('live', `实时更新 · ${lines.length} 行`);
            }
        } catch (error) {
            console.error('获取日志失败:', error);
            this.setLogIndicator('error', '日志连接异常');
            this.renderLogError(error.message || '未知错误');
        }
    }

    renderLogError(message) {
        const logContainer = document.getElementById('logStreamContent');
        if (!logContainer) return;
        logContainer.innerHTML = `
            <span class="log-line error">[日志连接异常]</span>
            <span class="log-line warn">${this.escapeHtml(message)}</span>
            <span class="log-line info">你可以点击右上角刷新按钮重试。</span>
        `;
    }

    renderLogLines(lines) {
        const logContainer = document.getElementById('logStreamContent');
        if (!logContainer) return;

        if (!lines || lines.length === 0) {
            logContainer.textContent = '暂无转录日志，请先发起一次任务。';
            return;
        }

        logContainer.innerHTML = lines.map((line) => {
            const levelClass = this.detectLogLevel(line);

            const lineContent = this.highlightKeyword(line, this.logFilters.keyword);

            return `<span class="log-line ${levelClass}">${lineContent}</span>`;
        }).join('');

        if (this.logsAutoScroll) {
            logContainer.scrollTop = logContainer.scrollHeight;
        }
    }

    detectLogLevel(line) {
        const lower = line.toLowerCase();
        if (lower.includes('| error') || lower.includes('| critical') || lower.includes('失败') || lower.includes('异常')) {
            return 'error';
        }
        if (lower.includes('| warning') || lower.includes('| warn') || lower.includes('超时')) {
            return 'warn';
        }
        return 'info';
    }

    highlightKeyword(line, keyword) {
        const escaped = this.escapeHtml(line);
        if (!keyword) {
            return escaped;
        }

        const escapedKeyword = this.escapeRegExp(keyword);
        const matcher = new RegExp(`(${escapedKeyword})`, 'gi');
        return escaped.replace(matcher, '<mark>$1</mark>');
    }

    escapeRegExp(value) {
        return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }

    exportCurrentLogs() {
        if (!this.currentLogLines || this.currentLogLines.length === 0) {
            this.showToast('当前没有可导出的日志', 'warning');
            return;
        }

        const now = new Date();
        const timestamp = `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}-${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}${String(now.getSeconds()).padStart(2, '0')}`;
        const fileName = `transcription-logs-${timestamp}.txt`;
        const header = [
            `Video Transcriber Logs`,
            `level=${this.logFilters.level}`,
            `keyword=${this.logFilters.keyword || '(none)'}`,
            `exported_at=${new Date().toISOString()}`,
            `----------------------------------------`
        ].join('\n');
        const content = `${header}\n${this.currentLogLines.join('\n')}`;

        const blob = new Blob([content], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = fileName;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        this.showToast('日志片段已导出', 'success');
    }

    setLogIndicator(status, text) {
        const dot = document.getElementById('logStatusDot');
        const label = document.getElementById('logStatusText');
        if (!dot || !label) return;

        dot.classList.remove('paused', 'error');
        if (status === 'paused') {
            dot.classList.add('paused');
        } else if (status === 'error') {
            dot.classList.add('error');
        }

        label.textContent = text;
    }

    escapeHtml(value) {
        return value
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#039;');
    }

    handleFileSelect(file) {
        if (!file) return;

        // 验证文件类型（视频或音频）
        if (!file.type.startsWith('video/') && !file.type.startsWith('audio/')) {
            this.showToast('请选择视频或音频文件', 'warning');
            return;
        }

        // 验证文件大小 (1GB)
        const maxSize = 1024 * 1024 * 1024;
        if (file.size > maxSize) {
            this.showToast('文件大小不能超过1GB', 'warning');
            return;
        }

        this.selectedFile = file;

        // 显示文件信息
        document.querySelector('.upload-placeholder').style.display = 'none';
        document.getElementById('fileInfo').style.display = 'block';
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('fileSize').textContent = this.formatFileSize(file.size);

        // 启用转录按钮，显示文件状态条
        this.updateTranscribeButtonsEnabled(true);
        this.showFileStatusBar(file);
    }

    removeSelectedFile() {
        this.selectedFile = null;
        document.getElementById('videoFile').value = '';
        document.querySelector('.upload-placeholder').style.display = 'block';
        document.getElementById('fileInfo').style.display = 'none';
        this.updateTranscribeButtonsEnabled(false);
        this.hideFileStatusBar();
    }

    updateTranscribeButtonsEnabled(enabled) {
        const transcribeBtn = document.getElementById('transcribeBtn');
        const quickBtn = document.getElementById('transcribeQuickBtn');

        if (transcribeBtn) {
            transcribeBtn.disabled = !enabled;
        }

        if (quickBtn) {
            quickBtn.disabled = !enabled;
        }
    }

    handleBatchFilesSelect(files) {
        if (!files || files.length === 0) return;

        // 验证文件数量
        if (files.length > 10) {
            this.showToast('单次最多支持10个文件', 'warning');
            return;
        }

        // 验证文件类型和大小
        const maxSize = 1024 * 1024 * 1024;  // 1GB
        this.selectedBatchFiles = [];

        for (const file of Array.from(files)) {
            if (!file.type.startsWith('video/') && !file.type.startsWith('audio/')) {
                this.showToast(`跳过不支持的文件: ${file.name}`, 'warning');
                continue;
            }
            if (file.size > maxSize) {
                this.showToast(`文件过大(跳过): ${file.name}`, 'warning');
                continue;
            }
            this.selectedBatchFiles.push(file);
        }

        if (this.selectedBatchFiles.length === 0) {
            this.showToast('没有有效的媒体文件', 'warning');
            return;
        }

        // 显示文件列表
        this.displaySelectedFiles();

        // 启用批量转录按钮
        document.getElementById('batchTranscribeBtn').disabled = false;
    }

    displaySelectedFiles() {
        const container = document.getElementById('selectedFiles');
        const fileList = document.getElementById('fileList');

        container.style.display = 'block';

        fileList.innerHTML = this.selectedBatchFiles.map((file, index) => `
            <div class="file-item">
                <div class="d-flex align-items-center">
                    <i class="bi bi-file-earmark-play me-2"></i>
                    <div class="flex-grow-1">
                        <div class="file-name">${file.name}</div>
                        <small class="text-muted">${this.formatFileSize(file.size)}</small>
                    </div>
                    <span class="badge bg-primary">#${index + 1}</span>
                </div>
            </div>
        `).join('');
    }

    initWebSocket() {
        try {
            this.ws = new WebSocket(this.wsUrl);

            this.ws.onopen = () => {
                console.log('WebSocket连接建立');
            };

            this.ws.onmessage = (event) => {
                try {
                    const message = JSON.parse(event.data);
                    this.handleWebSocketMessage(message);
                } catch (error) {
                    console.error('WebSocket消息解析失败:', error);
                }
            };

            this.ws.onclose = () => {
                console.log('WebSocket连接关闭');
                setTimeout(() => this.initWebSocket(), 5000);
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket错误:', error);
            };

        } catch (error) {
            console.error('WebSocket初始化失败:', error);
        }
    }

    handleWebSocketMessage(message) {
        const { type, data } = message;

        switch (type) {
            case 'progress':
                this.updateProgress(data);
                break;
            case 'result':
                this.displayResult(data);
                break;
            case 'error':
                this.showError(data.error);
                break;
            default:
                console.log('未知WebSocket消息类型:', type);
        }
    }

    async handleSingleTranscribe() {
        if (!this.selectedFile) {
            this.showToast('请先选择视频文件', 'warning');
            return;
        }

        const btn = document.getElementById('transcribeBtn');
        const quickBtn = document.getElementById('transcribeQuickBtn');

        // 禁用表单
        this.toggleForm(false);
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>处理中...';
        const badge = document.querySelector('.file-status-badge');
        if (badge) {
            badge.textContent = '处理中';
            badge.classList.add('processing');
        }
        if (quickBtn) {
            quickBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>处理中...';
            quickBtn.disabled = true;
        }
        this.setLogIndicator('live', '任务执行中');
        this.fetchLogStream();

        try {
            // 显示进度卡片
            this.showProgressCard();

            // 使用文件上传方式
            const formData = new FormData();
            formData.append('file', this.selectedFile);
            formData.append('model', document.getElementById('model').value);
            formData.append('language', document.getElementById('language').value);
            formData.append('with_timestamps', document.getElementById('timestamps').checked);
            formData.append('output_format', document.getElementById('outputFormat').value);

            const response = await fetch(`${this.apiBaseUrl}/api/v1/transcribe/file`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.code === 200) {
                this.displayResultFromAPI(result.data.transcription);
                this.showToast('转录完成!', 'success');
            } else {
                throw new Error(result.message);
            }

        } catch (error) {
            console.error('转录请求失败:', error);
            this.showError(error.message);
        } finally {
            this.toggleForm(true);
            btn.innerHTML = '<i class="bi bi-play-fill me-2"></i>开始转录';
            const badge = document.querySelector('.file-status-badge');
            if (badge) {
                badge.textContent = '已就绪';
                badge.classList.remove('processing');
            }
            if (quickBtn) {
                quickBtn.innerHTML = '<i class="bi bi-play-circle-fill me-2"></i>立即转录';
                quickBtn.disabled = !this.selectedFile;
            }
            this.fetchRealtimeStatus();
            this.fetchLogStream();
        }
    }

    async handleBatchTranscribe() {
        if (this.selectedBatchFiles.length === 0) {
            this.showToast('请先选择视频文件', 'warning');
            return;
        }

        const btn = document.getElementById('batchTranscribeBtn');

        try {
            btn.disabled = true;
            btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>处理中...';
            this.setLogIndicator('live', '批量任务执行中');
            this.fetchLogStream();

            const formData = new FormData();
            this.selectedBatchFiles.forEach(file => {
                formData.append('files', file);
            });
            formData.append('model', document.getElementById('batchModel').value);
            formData.append('language', 'auto');
            formData.append('max_concurrent', document.getElementById('maxConcurrent').value);

            const response = await fetch(`${this.apiBaseUrl}/api/v1/transcribe/batch`, {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.code === 200) {
                this.showBatchProgress();
                this.showToast('批量任务已启动', 'success');
            } else {
                throw new Error(result.message);
            }

        } catch (error) {
            console.error('批量转录失败:', error);
            this.showToast(`批量转录失败: ${error.message}`, 'error');
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-play-fill me-2"></i>开始批量转录';
            this.fetchRealtimeStatus();
            this.fetchLogStream();
        }
    }

    showProgressCard() {
        const progressCard = document.getElementById('progressCard');
        const resultCard = document.getElementById('resultCard');

        progressCard.style.display = 'block';
        resultCard.style.display = 'none';

        this.updateProgress({ progress: 0, message: '上传文件中...' });
    }

    updateProgress(data) {
        const progressBar = document.getElementById('progressBar');
        const progressText = document.getElementById('progressText');

        const progress = data.progress || 0;
        const message = data.message || '处理中...';

        progressBar.style.width = `${progress}%`;
        progressBar.setAttribute('aria-valuenow', progress);
        progressText.textContent = message;
    }

    displayResultFromAPI(data) {
        const progressCard = document.getElementById('progressCard');
        const resultCard = document.getElementById('resultCard');
        const resultContent = document.getElementById('resultContent');
        const resultStats = document.getElementById('resultStats');

        // 隐藏进度，显示结果
        progressCard.style.display = 'none';
        resultCard.style.display = 'block';

        // 格式化结果内容
        const format = document.getElementById('outputFormat').value;
        let content = '';

        if (format === 'json') {
            content = JSON.stringify(data, null, 2);
            resultContent.className = 'result-content json';
        } else if (format === 'srt' || format === 'vtt') {
            content = this.formatSubtitles(data, format);
            resultContent.className = `result-content ${format}`;
        } else {
            content = data.text || '';
            resultContent.className = 'result-content';
        }

        resultContent.textContent = content;

        // 显示统计信息
        if (data.confidence !== undefined) {
            resultStats.innerHTML = `
                <div class="row g-2">
                    <div class="col-auto">
                        <span class="badge bg-primary">置信度: ${(data.confidence * 100).toFixed(1)}%</span>
                    </div>
                    <div class="col-auto">
                        <span class="badge bg-info">语言: ${data.language}</span>
                    </div>
                    <div class="col-auto">
                        <span class="badge bg-success">长度: ${data.text ? data.text.length : 0} 字符</span>
                    </div>
                </div>
            `;
        }

        // 保存到历史记录
        this.saveToHistory({
            path: this.selectedFile ? this.selectedFile.name : '未知',
            result: data,
            timestamp: new Date().toISOString(),
            format: format
        });
    }

    displayResult(data) {
        this.displayResultFromAPI(data);
        this.showToast('转录完成!', 'success');
    }

    showBatchProgress() {
        const progressDiv = document.getElementById('batchProgress');
        const taskList = document.getElementById('batchTaskList');

        progressDiv.style.display = 'block';

        // 清空任务列表
        taskList.innerHTML = '';

        // 创建任务项
        this.selectedBatchFiles.forEach((file, index) => {
            const taskItem = document.createElement('div');
            taskItem.className = 'batch-task-item';
            taskItem.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div class="flex-grow-1">
                        <div class="task-path">${file.name}</div>
                        <div class="task-status pending" id="task-status-${index}">等待中</div>
                    </div>
                    <div class="task-progress">
                        <div class="progress" style="width: 60px; height: 4px;">
                            <div class="progress-bar" id="task-progress-${index}"></div>
                        </div>
                    </div>
                </div>
            `;
            taskList.appendChild(taskItem);
        });
    }

    formatSubtitles(data, format) {
        if (!data.segments || data.segments.length === 0) {
            return data.text || '';
        }

        if (format === 'srt') {
            return data.segments.map((segment, index) => {
                const start = this.formatTime(segment.start_time, 'srt');
                const end = this.formatTime(segment.end_time, 'srt');
                return `${index + 1}\n${start} --> ${end}\n${segment.text}\n`;
            }).join('\n');
        } else if (format === 'vtt') {
            let result = 'WEBVTT\n\n';
            result += data.segments.map(segment => {
                const start = this.formatTime(segment.start_time, 'vtt');
                const end = this.formatTime(segment.end_time, 'vtt');
                return `${start} --> ${end}\n${segment.text}\n`;
            }).join('\n');
            return result;
        }

        return data.text || '';
    }

    formatTime(seconds, format) {
        const hours = Math.floor(seconds / 3600);
        const minutes = Math.floor((seconds % 3600) / 60);
        const secs = seconds % 60;

        if (format === 'srt') {
            const millisecs = Math.floor((secs % 1) * 1000);
            const secsInt = Math.floor(secs);
            return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secsInt.toString().padStart(2, '0')},${millisecs.toString().padStart(3, '0')}`;
        } else if (format === 'vtt') {
            return `${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${secs.toFixed(3).padStart(6, '0')}`;
        }

        return '';
    }

    copyResult() {
        const resultContent = document.getElementById('resultContent');
        const text = resultContent.textContent;

        navigator.clipboard.writeText(text).then(() => {
            this.showToast('结果已复制到剪贴板', 'success');
        }).catch(() => {
            this.showToast('复制失败', 'error');
        });
    }

    downloadResult() {
        const resultContent = document.getElementById('resultContent');
        const text = resultContent.textContent;
        const format = document.getElementById('outputFormat').value;

        // 使用上传文件名作为下载文件名
        let fileName = 'transcription';
        console.log('下载调试 - selectedFile:', this.selectedFile);
        if (this.selectedFile && this.selectedFile.name) {
            // 去掉原始文件扩展名
            const nameWithoutExt = this.selectedFile.name.replace(/\.[^/.]+$/, '');
            fileName = nameWithoutExt;
            console.log('下载调试 - 使用文件名:', fileName);
        }

        console.log('下载调试 - 最终文件名:', `${fileName}.${format}`);

        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = `${fileName}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        this.showToast('文件下载已开始', 'success');
    }

    clearResult() {
        if (confirm('确定要清空当前转录结果吗？')) {
            const resultCard = document.getElementById('resultCard');
            const resultContent = document.getElementById('resultContent');
            const resultStats = document.getElementById('resultStats');

            // 清空内容
            resultContent.textContent = '';
            resultStats.innerHTML = '';

            // 隐藏结果卡片
            resultCard.style.display = 'none';

            this.showToast('转录结果已清空', 'success');
        }
    }

    toggleForm(enabled) {
        const inputs = document.querySelectorAll('#single input, #single select, #single button:not(#copyBtn):not(#downloadBtn):not(#clearResultBtn):not(#removeFileBtn)');

        inputs.forEach(input => {
            input.disabled = !enabled;
        });

        const quickBtn = document.getElementById('transcribeQuickBtn');
        if (quickBtn) {
            quickBtn.disabled = !enabled || !this.selectedFile;
        }
    }

    showError(message) {
        this.showToast(message, 'error');
        this.setLogIndicator('error', '任务异常');

        // 重新启用表单
        this.toggleForm(true);

        // 隐藏进度卡片
        document.getElementById('progressCard').style.display = 'none';
    }

    showToast(message, type = 'info') {
        const toast = document.getElementById('toast');
        const toastBody = document.getElementById('toastBody');

        // 设置消息内容
        toastBody.textContent = message;

        // 设置样式
        const toastHeader = toast.querySelector('.toast-header');
        toastHeader.className = `toast-header bg-${type === 'error' ? 'danger' : type} text-${type === 'warning' ? 'dark' : 'white'}`;

        // 显示Toast
        const bsToast = new bootstrap.Toast(toast);
        bsToast.show();
    }

    saveToHistory(item) {
        this.history.unshift(item);
        // 只保留最近50条记录
        if (this.history.length > 50) {
            this.history = this.history.slice(0, 50);
        }
        localStorage.setItem('transcription_history', JSON.stringify(this.history));
        this.displayHistory();
    }

    loadHistory() {
        try {
            const stored = localStorage.getItem('transcription_history');
            return stored ? JSON.parse(stored) : [];
        } catch {
            return [];
        }
    }

    displayHistory() {
        const historyList = document.getElementById('historyList');

        if (this.history.length === 0) {
            historyList.innerHTML = `
                <div class="text-center text-muted py-4">
                    <i class="bi bi-inbox display-4"></i>
                    <p class="mt-2">暂无转录历史</p>
                </div>
            `;
            return;
        }

        historyList.innerHTML = this.history.map((item, index) => `
            <div class="history-item fade-in">
                <div class="history-title">${this.extractTitle(item.path)}</div>
                <div class="history-meta">
                    <span class="me-3">
                        <i class="bi bi-file-earmark-play me-1"></i>
                        ${item.path}
                    </span>
                    <span class="me-3">
                        <i class="bi bi-clock me-1"></i>
                        ${this.formatTimestamp(item.timestamp)}
                    </span>
                    <span class="badge bg-secondary">${item.format}</span>
                </div>
                <div class="history-content" id="history-content-${index}">
                    ${this.truncateText(item.result.text || '', 200)}
                </div>
                <div class="history-actions">
                    <button class="btn btn-sm btn-outline-primary me-2" onclick="ui.expandHistory(${index})">
                        <i class="bi bi-arrows-expand"></i> 展开
                    </button>
                    <button class="btn btn-sm btn-outline-success me-2" onclick="ui.copyHistoryItem(${index})">
                        <i class="bi bi-clipboard"></i> 复制
                    </button>
                    <button class="btn btn-sm btn-outline-danger" onclick="ui.deleteHistoryItem(${index})">
                        <i class="bi bi-trash"></i> 删除
                    </button>
                </div>
            </div>
        `).join('');
    }

    expandHistory(index) {
        const contentEl = document.getElementById(`history-content-${index}`);
        const item = this.history[index];

        if (contentEl.classList.contains('expanded')) {
            contentEl.classList.remove('expanded');
            contentEl.innerHTML = this.truncateText(item.result.text || '', 200);
        } else {
            contentEl.classList.add('expanded');
            contentEl.innerHTML = item.result.text || '';
        }
    }

    copyHistoryItem(index) {
        const item = this.history[index];
        const text = item.result.text || '';

        navigator.clipboard.writeText(text).then(() => {
            this.showToast('历史记录已复制', 'success');
        }).catch(() => {
            this.showToast('复制失败', 'error');
        });
    }

    deleteHistoryItem(index) {
        if (confirm('确定要删除这条历史记录吗？')) {
            this.history.splice(index, 1);
            localStorage.setItem('transcription_history', JSON.stringify(this.history));
            this.displayHistory();
            this.showToast('历史记录已删除', 'success');
        }
    }

    clearHistory() {
        if (confirm('确定要清空所有历史记录吗？此操作不可恢复。')) {
            this.history = [];
            localStorage.removeItem('transcription_history');
            this.displayHistory();
            this.showToast('历史记录已清空', 'success');
        }
    }

    extractTitle(path) {
        const fileName = path.split(/[/\\]/).pop() || path;
        return fileName;
    }

    formatTimestamp(timestamp) {
        const date = new Date(timestamp);
        const now = new Date();
        const diff = now - date;

        if (diff < 60000) {
            return '刚刚';
        } else if (diff < 3600000) {
            return `${Math.floor(diff / 60000)}分钟前`;
        } else if (diff < 86400000) {
            return `${Math.floor(diff / 3600000)}小时前`;
        } else {
            return date.toLocaleDateString();
        }
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    truncateText(text, maxLength) {
        if (text.length <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength) + '...';
    }
}

// 初始化应用
const ui = new VideoTranscriberUI();

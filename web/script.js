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

        this.init();
    }

    init() {
        this.bindEvents();
        this.loadHistory();
        this.displayHistory();
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
            if (file && file.type.startsWith('video/')) {
                videoFileInput.files = e.dataTransfer.files;
                this.handleFileSelect(file);
            } else {
                this.showToast('请上传视频文件', 'warning');
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
            const files = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('video/'));
            if (files.length > 0) {
                batchFilesInput.files = e.dataTransfer.files;
                this.handleBatchFilesSelect(files);
            } else {
                this.showToast('请上传视频文件', 'warning');
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
    }

    handleFileSelect(file) {
        if (!file) return;

        // 验证文件类型
        if (!file.type.startsWith('video/')) {
            this.showToast('请选择视频文件', 'warning');
            return;
        }

        // 验证文件大小 (500MB)
        const maxSize = 500 * 1024 * 1024;
        if (file.size > maxSize) {
            this.showToast('文件大小不能超过500MB', 'warning');
            return;
        }

        this.selectedFile = file;

        // 显示文件信息
        document.querySelector('.upload-placeholder').style.display = 'none';
        document.getElementById('fileInfo').style.display = 'block';
        document.getElementById('fileName').textContent = file.name;
        document.getElementById('fileSize').textContent = this.formatFileSize(file.size);

        // 启用转录按钮
        document.getElementById('transcribeBtn').disabled = false;
    }

    removeSelectedFile() {
        this.selectedFile = null;
        document.getElementById('videoFile').value = '';
        document.querySelector('.upload-placeholder').style.display = 'block';
        document.getElementById('fileInfo').style.display = 'none';
        document.getElementById('transcribeBtn').disabled = true;
    }

    handleBatchFilesSelect(files) {
        if (!files || files.length === 0) return;

        // 验证文件数量
        if (files.length > 10) {
            this.showToast('单次最多支持10个文件', 'warning');
            return;
        }

        // 验证文件类型和大小
        const maxSize = 500 * 1024 * 1024;
        this.selectedBatchFiles = [];

        for (const file of Array.from(files)) {
            if (!file.type.startsWith('video/')) {
                this.showToast(`跳过非视频文件: ${file.name}`, 'warning');
                continue;
            }
            if (file.size > maxSize) {
                this.showToast(`文件过大(跳过): ${file.name}`, 'warning');
                continue;
            }
            this.selectedBatchFiles.push(file);
        }

        if (this.selectedBatchFiles.length === 0) {
            this.showToast('没有有效的视频文件', 'warning');
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

        // 禁用表单
        this.toggleForm(false);
        btn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>处理中...';

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

            const response = await fetch(`${this.apiBaseUrl}/api/v1/transcribe`, {
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

            const formData = new FormData();
            this.selectedBatchFiles.forEach(file => {
                formData.append('files', file);
            });
            formData.append('model', document.getElementById('batchModel').value);
            formData.append('language', 'auto');
            formData.append('max_concurrent', document.getElementById('maxConcurrent').value);

            const response = await fetch(`${this.apiBaseUrl}/api/v1/batch-transcribe`, {
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

        const blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = `transcription_${new Date().getTime()}.${format}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        this.showToast('文件下载已开始', 'success');
    }

    toggleForm(enabled) {
        const inputs = document.querySelectorAll('#single input, #single select, #single button:not(#copyBtn):not(#downloadBtn):not(#removeFileBtn)');

        inputs.forEach(input => {
            input.disabled = !enabled;
        });
    }

    showError(message) {
        this.showToast(message, 'error');

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

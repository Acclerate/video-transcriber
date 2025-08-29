// Video Transcriber Web界面交互脚本

class VideoTranscriberUI {
    constructor() {
        this.apiBaseUrl = window.location.origin;
        this.wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/transcribe`;
        this.ws = null;
        this.currentTaskId = null;
        this.batchTasks = new Map();
        this.history = this.loadHistory();
        
        this.init();
    }
    
    init() {
        this.bindEvents();
        this.loadHistory();
        this.displayHistory();
        this.initWebSocket();
    }
    
    bindEvents() {
        // 单个转录表单
        document.getElementById('transcribeForm').addEventListener('submit', (e) => {
            e.preventDefault();
            this.handleSingleTranscribe();
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
    
    initWebSocket() {
        try {
            this.ws = new WebSocket(this.wsUrl);
            
            this.ws.onopen = () => {
                console.log('WebSocket连接建立');
                this.updateConnectionStatus(true);
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
                this.updateConnectionStatus(false);
                // 5秒后重连
                setTimeout(() => this.initWebSocket(), 5000);
            };
            
            this.ws.onerror = (error) => {
                console.error('WebSocket错误:', error);
                this.updateConnectionStatus(false);
            };
            
        } catch (error) {
            console.error('WebSocket初始化失败:', error);
            this.updateConnectionStatus(false);
        }
    }
    
    updateConnectionStatus(isConnected) {
        // 可以添加连接状态指示器
        const indicator = document.querySelector('.status-indicator');
        if (indicator) {
            indicator.className = `status-indicator ${isConnected ? 'online' : 'offline'}`;
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
        const form = document.getElementById('transcribeForm');
        const btn = document.getElementById('transcribeBtn');
        const url = document.getElementById('videoUrl').value.trim();
        
        if (!url) {
            this.showToast('请输入视频链接', 'warning');
            return;
        }
        
        if (!this.validateUrl(url)) {
            this.showToast('请输入有效的视频链接', 'error');
            return;
        }
        
        // 禁用表单
        this.toggleForm(false);
        btn.innerHTML = '<span class="loading-spinner me-2"></span>处理中...';
        
        try {
            // 显示进度卡片
            this.showProgressCard();
            
            // 准备请求数据
            const requestData = {
                action: 'transcribe',
                data: {
                    url: url,
                    options: {
                        model: document.getElementById('model').value,
                        language: document.getElementById('language').value,
                        with_timestamps: document.getElementById('timestamps').checked,
                        output_format: document.getElementById('outputFormat').value
                    }
                }
            };
            
            // 通过WebSocket发送请求
            if (this.ws && this.ws.readyState === WebSocket.OPEN) {
                this.ws.send(JSON.stringify(requestData));
            } else {
                throw new Error('WebSocket连接未建立');
            }
            
        } catch (error) {
            console.error('转录请求失败:', error);
            this.showError(error.message);
            this.toggleForm(true);
            btn.innerHTML = '<i class="bi bi-play-fill me-2"></i>开始转录';
        }
    }
    
    async handleBatchTranscribe() {
        const urlsText = document.getElementById('batchUrls').value.trim();
        const btn = document.getElementById('batchTranscribeBtn');
        
        if (!urlsText) {
            this.showToast('请输入视频链接列表', 'warning');
            return;
        }
        
        const urls = urlsText.split('\n')
            .map(url => url.trim())
            .filter(url => url && !url.startsWith('#'));
        
        if (urls.length === 0) {
            this.showToast('没有找到有效的视频链接', 'warning');
            return;
        }
        
        if (urls.length > 20) {
            this.showToast('最多支持20个视频链接', 'error');
            return;
        }
        
        // 验证所有URL
        const invalidUrls = urls.filter(url => !this.validateUrl(url));
        if (invalidUrls.length > 0) {
            this.showToast(`发现${invalidUrls.length}个无效链接`, 'error');
            return;
        }
        
        try {
            btn.disabled = true;
            btn.innerHTML = '<span class="loading-spinner me-2"></span>处理中...';
            
            const requestData = {
                urls: urls,
                options: {
                    model: document.getElementById('batchModel').value,
                    language: 'auto',
                    output_format: 'txt'
                },
                max_concurrent: parseInt(document.getElementById('maxConcurrent').value)
            };
            
            const response = await fetch(`${this.apiBaseUrl}/api/v1/batch-transcribe`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestData)
            });
            
            const result = await response.json();
            
            if (result.code === 200) {
                this.showBatchProgress(urls);
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
        
        this.updateProgress({ progress: 0, message: '准备中...' });
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
    
    displayResult(data) {
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
                    <div class="col-auto">
                        <span class="badge bg-warning">模型: ${data.model_used}</span>
                    </div>
                </div>
            `;
        }
        
        // 保存到历史记录
        this.saveToHistory({
            url: document.getElementById('videoUrl').value,
            result: data,
            timestamp: new Date().toISOString(),
            format: format
        });
        
        // 重新启用表单
        this.toggleForm(true);
        const btn = document.getElementById('transcribeBtn');
        btn.innerHTML = '<i class="bi bi-play-fill me-2"></i>开始转录';
        
        this.showToast('转录完成!', 'success');
    }
    
    showBatchProgress(urls) {
        const progressDiv = document.getElementById('batchProgress');
        const taskList = document.getElementById('batchTaskList');
        
        progressDiv.style.display = 'block';
        
        // 清空任务列表
        taskList.innerHTML = '';
        
        // 创建任务项
        urls.forEach((url, index) => {
            const taskItem = document.createElement('div');
            taskItem.className = 'batch-task-item';
            taskItem.innerHTML = `
                <div class="d-flex justify-content-between align-items-center">
                    <div class="flex-grow-1">
                        <div class="task-url">${this.truncateUrl(url)}</div>
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
        const form = document.getElementById('transcribeForm');
        const inputs = form.querySelectorAll('input, select, button');
        
        inputs.forEach(input => {
            input.disabled = !enabled;
        });
    }
    
    validateUrl(url) {
        try {
            const urlObj = new URL(url);
            const supportedDomains = [
                'douyin.com', 'iesdouyin.com', 'v.douyin.com',
                'bilibili.com', 'b23.tv'
            ];
            
            return supportedDomains.some(domain => 
                urlObj.hostname.includes(domain)
            );
        } catch {
            return false;
        }
    }
    
    truncateUrl(url) {
        if (url.length <= 50) return url;
        return url.substring(0, 47) + '...';
    }
    
    showError(message) {
        this.showToast(message, 'error');
        
        // 重新启用表单
        this.toggleForm(true);
        const btn = document.getElementById('transcribeBtn');
        btn.innerHTML = '<i class="bi bi-play-fill me-2"></i>开始转录';
        
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
                <div class="history-title">${this.extractTitle(item.url)}</div>
                <div class="history-meta">
                    <span class="me-3">
                        <i class="bi bi-link-45deg me-1"></i>
                        ${this.truncateUrl(item.url)}
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
    
    extractTitle(url) {
        try {
            const urlObj = new URL(url);
            if (urlObj.hostname.includes('douyin')) {
                return '抖音视频';
            } else if (urlObj.hostname.includes('bilibili')) {
                return 'B站视频';
            } else {
                return '未知视频';
            }
        } catch {
            return '视频转录';
        }
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
    
    truncateText(text, maxLength) {
        if (text.length <= maxLength) {
            return text;
        }
        return text.substring(0, maxLength) + '...';
    }
}

// 初始化应用
const ui = new VideoTranscriberUI();
// Socket.IO客户端连接
const socket = io();

// 连接状态
socket.on('connect', function() {
    console.log('✓ 已连接到服务器');
    showNotification('已连接到服务器', 'success');
});

socket.on('disconnect', function() {
    console.log('✗ 与服务器断开连接');
    showNotification('与服务器断开连接', 'warning');
});

socket.on('connected', function(data) {
    console.log('Server message:', data);
});

// 接收进度更新
socket.on('progress', function(data) {
    console.log('Progress update:', data);

    // 更新进度条
    if (data.percent !== undefined) {
        updateProgressBar(data.percent, data.current, data.total);
    }

    // 更新当前商品信息
    if (data.current_url) {
        updateCurrentItem(data);
    }

    // 更新统计信息
    if (data.statistics) {
        updateStatistics(data.statistics);
    }
});

// 接收日志
socket.on('log', function(data) {
    console.log(`[${data.timestamp}] [${data.level}] ${data.message}`);
    appendLog(data);
});

// 显示通知
function showNotification(message, type = 'info') {
    // 创建toast通知
    const toastContainer = document.getElementById('toast-container');
    if (!toastContainer) {
        const container = document.createElement('div');
        container.id = 'toast-container';
        container.className = 'toast-container position-fixed top-0 end-0 p-3';
        document.body.appendChild(container);
    }

    const toastId = 'toast-' + Date.now();
    const toastHTML = `
        <div id="${toastId}" class="toast align-items-center text-white bg-${type} border-0" role="alert">
            <div class="d-flex">
                <div class="toast-body">
                    ${message}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
            </div>
        </div>
    `;

    document.getElementById('toast-container').insertAdjacentHTML('beforeend', toastHTML);

    const toastElement = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastElement, { delay: 3000 });
    toast.show();

    // 移除已显示的toast
    toastElement.addEventListener('hidden.bs.toast', function() {
        toastElement.remove();
    });
}

// 更新进度条
function updateProgressBar(percent, current, total) {
    const progressBar = document.getElementById('progress-bar');
    if (progressBar) {
        progressBar.style.width = percent + '%';
        progressBar.setAttribute('aria-valuenow', percent);
        progressBar.textContent = `${percent}% (${current}/${total})`;
    }

    const progressText = document.getElementById('progress-text');
    if (progressText) {
        progressText.textContent = `进度: ${current} / ${total}`;
    }
}

// 更新当前商品信息
function updateCurrentItem(data) {
    const currentUrl = document.getElementById('current-url');
    if (currentUrl) {
        currentUrl.textContent = data.current_url || '';
    }

    const currentStatus = document.getElementById('current-status');
    if (currentStatus) {
        let statusHTML = '';
        if (data.status === 'processing') {
            statusHTML = '<span class="text-info">正在处理...</span>';
        } else if (data.status === 'success') {
            statusHTML = `<span class="text-success">✓ 成功: ¥${data.original_price} / ¥${data.promo_price}</span>`;
        } else if (data.status === 'failed') {
            statusHTML = '<span class="text-danger">✗ 失败</span>';
        }
        currentStatus.innerHTML = statusHTML;
    }
}

// 更新统计信息
function updateStatistics(stats) {
    const elements = {
        'stat-success': stats.success,
        'stat-failed': stats.failed,
        'stat-unavailable': stats.unavailable,
        'stat-total': stats.total
    };

    for (const [id, value] of Object.entries(elements)) {
        const element = document.getElementById(id);
        if (element) {
            element.textContent = value;
        }
    }
}

// 添加日志条目
function appendLog(data) {
    const logContainer = document.getElementById('log-entries');
    if (!logContainer) return;

    const logEntry = document.createElement('div');
    logEntry.className = 'log-entry';

    const levelClass = `log-level-${data.level}`;
    const timestamp = `<span class="log-timestamp">[${data.timestamp}]</span>`;
    const level = `<span class="${levelClass}">[${data.level}]</span>`;
    const message = `<span>${data.message}</span>`;

    logEntry.innerHTML = `${timestamp} ${level} ${message}`;

    // 添加到容器顶部（最新的在上面）
    logContainer.insertBefore(logEntry, logContainer.firstChild);

    // 限制日志数量（保留最新的100条）
    while (logContainer.children.length > 100) {
        logContainer.removeChild(logContainer.lastChild);
    }
}

console.log('Socket.IO client initialized');

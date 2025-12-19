// 主要JavaScript功能

// 格式化日期时间
function formatDateTime(dateStr) {
    const date = new Date(dateStr);
    return date.toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

// 格式化持续时间
function formatDuration(seconds) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hours > 0) {
        return `${hours}小时${minutes}分${secs}秒`;
    } else if (minutes > 0) {
        return `${minutes}分${secs}秒`;
    } else {
        return `${secs}秒`;
    }
}

// Ajax请求封装
function apiRequest(url, method = 'GET', data = null) {
    const options = {
        method: method,
        headers: {
            'Content-Type': 'application/json'
        }
    };

    if (data && method !== 'GET') {
        options.body = JSON.stringify(data);
    }

    return fetch(url, options)
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        });
}

// 显示加载动画
function showLoading(elementId, text = '加载中...') {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `
            <div class="text-center py-5">
                <div class="spinner-border text-primary" role="status">
                    <span class="visually-hidden">Loading...</span>
                </div>
                <p class="mt-3 text-muted">${text}</p>
            </div>
        `;
    }
}

// 显示错误信息
function showError(elementId, message) {
    const element = document.getElementById(elementId);
    if (element) {
        element.innerHTML = `
            <div class="alert alert-danger" role="alert">
                <i class="bi bi-exclamation-triangle"></i>
                ${message}
            </div>
        `;
    }
}

// 文件上传 - 拖拽支持
function initFileUpload(uploadAreaId, fileInputId, onFileSelect) {
    const uploadArea = document.getElementById(uploadAreaId);
    const fileInput = document.getElementById(fileInputId);

    if (!uploadArea || !fileInput) return;

    // 点击上传区域触发文件选择
    uploadArea.addEventListener('click', function() {
        fileInput.click();
    });

    // 文件选择
    fileInput.addEventListener('change', function(e) {
        if (e.target.files.length > 0) {
            onFileSelect(e.target.files[0]);
        }
    });

    // 拖拽事件
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
    });

    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');

        const files = e.dataTransfer.files;
        if (files.length > 0) {
            fileInput.files = files;
            onFileSelect(files[0]);
        }
    });
}

// 导出表格为CSV
function exportTableToExcel(tableId, filename = 'export.xlsx') {
    // 这里可以使用库如SheetJS来导出Excel
    // 简单版本：导出为CSV
    const table = document.getElementById(tableId);
    if (!table) return;

    let csv = [];
    const rows = table.querySelectorAll('tr');

    for (let row of rows) {
        let rowData = [];
        const cols = row.querySelectorAll('td, th');

        for (let col of cols) {
            rowData.push(col.innerText);
        }

        csv.push(rowData.join(','));
    }

    const csvString = csv.join('\n');
    const blob = new Blob(['\ufeff' + csvString], { type: 'text/csv;charset=utf-8;' });

    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
}

// 复制到剪贴板
function copyToClipboard(text) {
    navigator.clipboard.writeText(text).then(function() {
        showNotification('已复制到剪贴板', 'success');
    }, function(err) {
        showNotification('复制失败: ' + err, 'danger');
    });
}

// 确认对话框
function confirmAction(message, onConfirm) {
    if (confirm(message)) {
        onConfirm();
    }
}

// 状态徽章生成
function getStatusBadge(status) {
    const badges = {
        'success': '<span class="badge bg-success">成功</span>',
        'not_found': '<span class="badge bg-secondary">商品不存在</span>',
        'unavailable': '<span class="badge bg-warning">已下架</span>',
        'blocked': '<span class="badge bg-danger">反爬验证</span>',
        'forbidden': '<span class="badge bg-danger">403错误</span>',
        'retry': '<span class="badge bg-info">需要重试</span>'
    };

    return badges[status] || '<span class="badge bg-secondary">未知</span>';
}

// 页面初始化
document.addEventListener('DOMContentLoaded', function() {
    console.log('Page loaded');

    // 初始化所有工具提示
    const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
    tooltipTriggerList.map(function (tooltipTriggerEl) {
        return new bootstrap.Tooltip(tooltipTriggerEl);
    });

    // 初始化所有弹出框
    const popoverTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="popover"]'));
    popoverTriggerList.map(function (popoverTriggerEl) {
        return new bootstrap.Popover(popoverTriggerEl);
    });
});

/**
 * Cogmate Visual - Common Utilities
 */

const API_BASE = window.location.origin;

// Namespace 支持
const urlParams = new URLSearchParams(window.location.search);
const NAMESPACE = urlParams.get('ns') || 'default';

/**
 * 构建带 namespace 的 API URL
 * @param {string} endpoint - API 端点路径
 * @param {Object} params - 额外的查询参数
 * @returns {string} 完整的 URL
 */
function apiUrl(endpoint, params = {}) {
    const url = new URL(endpoint, API_BASE);
    if (NAMESPACE !== 'default') {
        url.searchParams.set('ns', NAMESPACE);
    }
    for (const [key, value] of Object.entries(params)) {
        if (value !== undefined && value !== null) {
            url.searchParams.set(key, value);
        }
    }
    return url.toString();
}

/**
 * Token 管理器
 */
const TokenManager = {
    KEY: 'brain_token',
    INFO_KEY: 'brain_token_info',
    get() { return sessionStorage.getItem(this.KEY); },
    getInfo() { 
        const i = sessionStorage.getItem(this.INFO_KEY); 
        return i ? JSON.parse(i) : null; 
    },
    set(token, info) { 
        sessionStorage.setItem(this.KEY, token); 
        sessionStorage.setItem(this.INFO_KEY, JSON.stringify(info)); 
    },
    clear() { 
        sessionStorage.removeItem(this.KEY); 
        sessionStorage.removeItem(this.INFO_KEY); 
    },
    getScope() { return this.getInfo()?.scope || 'none'; },
    canChat() { return ['full', 'qa_public'].includes(this.getScope()); },
    canBrowse() { return ['full', 'browse_public'].includes(this.getScope()); }
};

/**
 * 获取当前 token（从 URL 或 session）
 */
function getToken() {
    return urlParams.get('token') || TokenManager.get();
}

/**
 * 显示 namespace 标识（如果不是 default）
 */
function showNamespaceBadge() {
    if (NAMESPACE !== 'default') {
        const badge = document.createElement('div');
        badge.className = 'namespace-badge';
        badge.textContent = `ns: ${NAMESPACE}`;
        badge.style.cssText = `
            position: fixed;
            top: 10px;
            right: 10px;
            background: rgba(212, 160, 84, 0.9);
            color: #1a1a1a;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            z-index: 9999;
        `;
        document.body.appendChild(badge);
    }
}

// 页面加载时显示 namespace 标识
document.addEventListener('DOMContentLoaded', showNamespaceBadge);

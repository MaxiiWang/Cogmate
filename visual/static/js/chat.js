/**
 * Brain Visual - Chat Panel Component
 * 可复用的聊天面板组件
 */

class BrainChat {
    constructor(options = {}) {
        this.apiBase = options.apiBase || window.location.origin;
        this.token = options.token || new URLSearchParams(window.location.search).get('token');
        this.container = null;
        this.isOpen = options.isOpen !== false;
        this.messages = [];
        this.isLoading = false;
        
        this.init();
    }
    
    init() {
        this.createStyles();
        this.createPanel();
        this.bindEvents();
        
        // Welcome message
        this.addMessage('bot', '你好！我是 Brain，可以帮你查询模拟世界中的知识。\n\n试试问我：\n• 「我对AI的看法是什么？」\n• 「为什么我对副业有顾虑？」\n• 「该不该现在辞职？」');
    }
    
    createStyles() {
        if (document.getElementById('brain-chat-styles')) return;
        
        const style = document.createElement('style');
        style.id = 'brain-chat-styles';
        style.textContent = `
            .brain-chat-toggle {
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 60px;
                height: 60px;
                border-radius: 50%;
                background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
                border: none;
                cursor: pointer;
                box-shadow: 0 4px 20px rgba(78, 205, 196, 0.4);
                z-index: 1000;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 1.5em;
                transition: transform 0.3s, box-shadow 0.3s;
            }
            .brain-chat-toggle:hover {
                transform: scale(1.1);
                box-shadow: 0 6px 25px rgba(78, 205, 196, 0.5);
            }
            .brain-chat-toggle.has-panel { display: none; }
            
            .brain-chat-panel {
                position: fixed;
                bottom: 20px;
                right: 20px;
                width: 400px;
                max-width: calc(100vw - 40px);
                height: 500px;
                max-height: calc(100vh - 100px);
                background: #12121a;
                border-radius: 16px;
                border: 1px solid #2a2a3a;
                box-shadow: 0 10px 50px rgba(0, 0, 0, 0.5);
                z-index: 1001;
                display: flex;
                flex-direction: column;
                overflow: hidden;
                transform: translateY(20px);
                opacity: 0;
                visibility: hidden;
                transition: all 0.3s ease;
            }
            .brain-chat-panel.open {
                transform: translateY(0);
                opacity: 1;
                visibility: visible;
            }
            
            .brain-chat-header {
                padding: 16px 20px;
                background: linear-gradient(135deg, rgba(78, 205, 196, 0.15) 0%, rgba(78, 205, 196, 0.05) 100%);
                border-bottom: 1px solid #2a2a3a;
                display: flex;
                align-items: center;
                justify-content: space-between;
            }
            .brain-chat-header h4 {
                color: #4ecdc4;
                font-size: 1em;
                font-weight: 600;
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .brain-chat-close {
                background: none;
                border: none;
                color: #666;
                font-size: 1.5em;
                cursor: pointer;
                padding: 0;
                line-height: 1;
                transition: color 0.2s;
            }
            .brain-chat-close:hover { color: #fff; }
            
            .brain-chat-messages {
                flex: 1;
                overflow-y: auto;
                padding: 20px;
                display: flex;
                flex-direction: column;
                gap: 15px;
            }
            .brain-chat-messages::-webkit-scrollbar {
                width: 6px;
            }
            .brain-chat-messages::-webkit-scrollbar-track {
                background: transparent;
            }
            .brain-chat-messages::-webkit-scrollbar-thumb {
                background: #333;
                border-radius: 3px;
            }
            
            .brain-chat-message {
                max-width: 85%;
                padding: 12px 16px;
                border-radius: 12px;
                font-size: 0.9em;
                line-height: 1.5;
                white-space: pre-wrap;
                word-break: break-word;
            }
            .brain-chat-message.user {
                align-self: flex-end;
                background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
                color: #fff;
                border-bottom-right-radius: 4px;
            }
            .brain-chat-message.bot {
                align-self: flex-start;
                background: rgba(255, 255, 255, 0.08);
                color: #ddd;
                border-bottom-left-radius: 4px;
            }
            .brain-chat-message.bot code {
                background: rgba(0,0,0,0.3);
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 0.85em;
            }
            .brain-chat-message.error {
                background: rgba(231, 76, 60, 0.2);
                color: #e74c3c;
            }
            
            .brain-chat-typing {
                display: flex;
                gap: 4px;
                padding: 12px 16px;
                background: rgba(255, 255, 255, 0.08);
                border-radius: 12px;
                width: fit-content;
            }
            .brain-chat-typing span {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: #4ecdc4;
                animation: typing 1.4s infinite ease-in-out both;
            }
            .brain-chat-typing span:nth-child(1) { animation-delay: -0.32s; }
            .brain-chat-typing span:nth-child(2) { animation-delay: -0.16s; }
            @keyframes typing {
                0%, 80%, 100% { transform: scale(0.6); opacity: 0.5; }
                40% { transform: scale(1); opacity: 1; }
            }
            
            .brain-chat-input-area {
                padding: 15px;
                border-top: 1px solid #2a2a3a;
                background: rgba(0, 0, 0, 0.2);
            }
            .brain-chat-input-wrapper {
                display: flex;
                gap: 10px;
            }
            .brain-chat-input {
                flex: 1;
                padding: 12px 16px;
                border: 1px solid #333;
                border-radius: 10px;
                background: rgba(255, 255, 255, 0.05);
                color: #fff;
                font-size: 0.9em;
                outline: none;
                transition: border-color 0.2s;
            }
            .brain-chat-input:focus {
                border-color: #4ecdc4;
            }
            .brain-chat-input::placeholder {
                color: #666;
            }
            .brain-chat-send {
                padding: 12px 20px;
                border: none;
                border-radius: 10px;
                background: linear-gradient(135deg, #4ecdc4 0%, #44a08d 100%);
                color: #fff;
                font-weight: 600;
                cursor: pointer;
                transition: transform 0.2s, box-shadow 0.2s;
            }
            .brain-chat-send:hover {
                transform: scale(1.05);
                box-shadow: 0 4px 15px rgba(78, 205, 196, 0.3);
            }
            .brain-chat-send:disabled {
                opacity: 0.5;
                cursor: not-allowed;
                transform: none;
            }
            
            .brain-chat-suggestions {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
                margin-top: 10px;
            }
            .brain-chat-suggestion {
                padding: 6px 12px;
                border: 1px solid #333;
                border-radius: 20px;
                background: transparent;
                color: #888;
                font-size: 0.8em;
                cursor: pointer;
                transition: all 0.2s;
            }
            .brain-chat-suggestion:hover {
                border-color: #4ecdc4;
                color: #4ecdc4;
            }
        `;
        document.head.appendChild(style);
    }
    
    createPanel() {
        // Toggle button
        const toggle = document.createElement('button');
        toggle.className = 'brain-chat-toggle';
        toggle.innerHTML = '💬';
        toggle.onclick = () => this.open();
        document.body.appendChild(toggle);
        this.toggleBtn = toggle;
        
        // Panel
        const panel = document.createElement('div');
        panel.className = 'brain-chat-panel';
        panel.innerHTML = `
            <div class="brain-chat-header">
                <h4>🧠 Brain Assistant</h4>
                <button class="brain-chat-close">×</button>
            </div>
            <div class="brain-chat-messages"></div>
            <div class="brain-chat-input-area">
                <div class="brain-chat-input-wrapper">
                    <input type="text" class="brain-chat-input" placeholder="输入问题...">
                    <button class="brain-chat-send">发送</button>
                </div>
                <div class="brain-chat-suggestions">
                    <button class="brain-chat-suggestion">我对AI的看法</button>
                    <button class="brain-chat-suggestion">最近的决策</button>
                    <button class="brain-chat-suggestion">知识库状态</button>
                </div>
            </div>
        `;
        document.body.appendChild(panel);
        this.container = panel;
        this.messagesEl = panel.querySelector('.brain-chat-messages');
        this.inputEl = panel.querySelector('.brain-chat-input');
        this.sendBtn = panel.querySelector('.brain-chat-send');
        
        if (this.isOpen) {
            this.open();
        }
    }
    
    bindEvents() {
        // Close button
        this.container.querySelector('.brain-chat-close').onclick = () => this.close();
        
        // Send button
        this.sendBtn.onclick = () => this.send();
        
        // Enter key
        this.inputEl.onkeypress = (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                this.send();
            }
        };
        
        // Suggestions
        this.container.querySelectorAll('.brain-chat-suggestion').forEach(btn => {
            btn.onclick = () => {
                this.inputEl.value = btn.textContent;
                this.send();
            };
        });
    }
    
    open() {
        this.container.classList.add('open');
        this.toggleBtn.classList.add('has-panel');
        this.inputEl.focus();
    }
    
    close() {
        this.container.classList.remove('open');
        this.toggleBtn.classList.remove('has-panel');
    }
    
    toggle() {
        if (this.container.classList.contains('open')) {
            this.close();
        } else {
            this.open();
        }
    }
    
    addMessage(role, content) {
        this.messages.push({ role, content });
        
        const msgEl = document.createElement('div');
        msgEl.className = `brain-chat-message ${role}`;
        msgEl.textContent = content;
        this.messagesEl.appendChild(msgEl);
        this.scrollToBottom();
    }
    
    showTyping() {
        const typing = document.createElement('div');
        typing.className = 'brain-chat-typing';
        typing.innerHTML = '<span></span><span></span><span></span>';
        typing.id = 'brain-chat-typing';
        this.messagesEl.appendChild(typing);
        this.scrollToBottom();
    }
    
    hideTyping() {
        const typing = document.getElementById('brain-chat-typing');
        if (typing) typing.remove();
    }
    
    scrollToBottom() {
        this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
    }
    
    async send() {
        const message = this.inputEl.value.trim();
        if (!message || this.isLoading) return;
        
        this.inputEl.value = '';
        this.addMessage('user', message);
        
        this.isLoading = true;
        this.sendBtn.disabled = true;
        this.showTyping();
        
        try {
            const response = await fetch(`${this.apiBase}/api/visual/chat?token=${this.token}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message })
            });
            
            if (!response.ok) {
                throw new Error('请求失败');
            }
            
            const data = await response.json();
            this.hideTyping();
            this.addMessage('bot', data.response || '暂无回复');
            
        } catch (error) {
            this.hideTyping();
            this.addMessage('error', '抱歉，请求失败：' + error.message);
        } finally {
            this.isLoading = false;
            this.sendBtn.disabled = false;
        }
    }
}

// Auto-init if token present
if (new URLSearchParams(window.location.search).get('token')) {
    window.brainChat = new BrainChat({ isOpen: false });
}

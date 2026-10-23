// 统一的「复制到剪贴板」实现。
//
// navigator.clipboard 只在安全上下文（https / localhost）可用；mybooks 大量部署是
// http:// 明文内网地址，这时 navigator.clipboard 是 undefined，直接调用会抛异常。
// 所以这里退回到临时 textarea + execCommand 的老路子（app/src/pages/opds-readme.vue
// 与 webdav-readme.vue 早就有同款写法，抽出来统一一份）。
//
// 返回 Promise<boolean> 而不是抛异常：调用方（分享弹窗、分享管理）要按结果决定
// 关不关窗、给什么提示，用返回值比用 try/catch 可读。

function legacyCopy(text) {
    if (typeof document === 'undefined' || !document.body) return false;
    const ta = document.createElement('textarea');
    ta.value = text;
    ta.setAttribute('readonly', '');
    // 不能 display:none / visibility:hidden，否则 select() 选不中内容，复制出来是空
    ta.style.position = 'fixed';
    ta.style.top = '0';
    ta.style.left = '-9999px';
    // iOS Safari 对字号 < 16px 的输入框聚焦会放大整页，固定 12pt 规避
    ta.style.fontSize = '12pt';
    let ok = false;
    // 用 try/finally 收尾：中途任何一步抛异常都要把临时节点清掉，别在 body 里留垃圾
    try {
        document.body.appendChild(ta);
        ta.select();
        // iOS Safari 不认 select()，必须显式设定选区
        ta.setSelectionRange(0, text.length);
        ok = document.execCommand('copy');
    } catch (e) {
        ok = false;
    } finally {
        if (ta.parentNode) ta.parentNode.removeChild(ta);
    }
    return ok;
}

export function copyText(text) {
    if (!text) return Promise.resolve(false);
    try {
        const canUseClipboard = typeof navigator !== 'undefined'
            && navigator.clipboard
            && typeof window !== 'undefined'
            && window.isSecureContext;
        if (canUseClipboard) {
            return navigator.clipboard.writeText(text)
                .then(() => true)
                .catch(() => legacyCopy(text));
        }
    } catch (e) {
        // 少数环境访问 navigator.clipboard 本身就会抛，落到下面的兜底
    }
    try {
        return Promise.resolve(legacyCopy(text));
    } catch (e) {
        return Promise.resolve(false);
    }
}

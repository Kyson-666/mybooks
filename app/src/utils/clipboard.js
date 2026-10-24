// 统一复制到剪贴板：安全上下文用 Clipboard API，否则用 execCommand 兜底。
// navigator.clipboard 只在安全上下文（https / localhost）可用；mybooks 大量部署是
// http:// 明文内网地址，这时 navigator.clipboard 是 undefined，直接调用会抛异常。
// 所以这里退回到临时 textarea + execCommand 的老路子（app/src/pages/opds-readme.vue
// 与 webdav-readme.vue 早就有同款写法，抽出来统一一份）。
//
// 返回 Promise<boolean> 而不是抛异常：调用方（分享弹窗、分享管理）要按结果决定
// 关不关窗、给什么提示，用返回值比用 try/catch 可读。

export function copyText(text) {
    if (!text) return Promise.resolve(false);
    const canUseClipboard = typeof navigator !== 'undefined'
        && navigator.clipboard
        && typeof window !== 'undefined'
        && window.isSecureContext;
    if (canUseClipboard) {
        return navigator.clipboard.writeText(text)
            .then(() => true)
            .catch(() => legacyCopy(text));
    }
    return Promise.resolve(legacyCopy(text));
}

function legacyCopy(text) {
    if (typeof document === 'undefined' || !document.body) return false;
    const holder = document.createElement('span');
    holder.textContent = text;
    holder.style.position = 'fixed';
    holder.style.top = '0';
    holder.style.left = '-9999px';
    holder.style.whiteSpace = 'pre';
    document.body.appendChild(holder);

    const range = document.createRange();
    range.selectNodeContents(holder);
    const selection = typeof window !== 'undefined' ? window.getSelection() : null;
    const saved = [];
    if (selection) {
        for (let i = 0; i < selection.rangeCount; i += 1) saved.push(selection.getRangeAt(i));
        selection.removeAllRanges();
        selection.addRange(range);
    }

    let ok = false;
    try {
        ok = document.execCommand('copy');
    } catch (e) {
        ok = false;
    }

    if (selection) {
        selection.removeAllRanges();
        saved.forEach((r) => selection.addRange(r));
    }
    if (holder.parentNode) holder.parentNode.removeChild(holder);
    return ok;
}

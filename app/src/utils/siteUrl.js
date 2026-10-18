/**
 * 对外链接的站点基地址。
 *
 * 管理员在「站点与外观 → 站点标识」里配了「网站默认访问链接」时优先用它：反代或多入口
 * （内网 IP + 对外域名）访问时，分享链接、二维码以及 OPDS/WebDAV 说明页里的地址
 * 不该跟着当前访问方式漂移。没配则回退当前访问地址，与改动前行为一致。
 *
 * 取值顺序：store.sys.siteUrl（/api/user/info 每次进页面刷新）→ localStorage 缓存
 * （首屏 AppHeader 请求还没回来时兜底）→ window.location.origin。
 *
 * store 里已经有值时不再看缓存——包括管理员清空后的空串：那种情况下缓存里还是上一次的
 * 旧地址，继续回退会把已经作废的域名又拿去拼分享链接。
 */
const SITE_URL_STORAGE_KEY = 'sys_site_url';

export function siteBaseUrl(store) {
    const sys = store && store.state ? store.state.sys : null;
    const fromStore = !!(sys && typeof sys.siteUrl === 'string');
    let url = fromStore ? sys.siteUrl : '';
    if (!fromStore && process.client && typeof localStorage !== 'undefined') {
        url = localStorage.getItem(SITE_URL_STORAGE_KEY) || '';
    }
    url = url.trim().replace(/\/+$/, '');
    if (url) return url;
    return typeof window !== 'undefined' ? window.location.origin : '';
}

export { SITE_URL_STORAGE_KEY };

/**
 * モメンタムチンパン — 順位変動ページ
 */

const H = {
    index: [],        // [{id, t, total, n}] 古い順
    ranks: null,      // {ids, names, ranks: {ticker: [[idx, rank], ...]}}
    cache: {},        // id -> snapshot
    from: null, to: null,
    market: 'ALL', scope: 50, view: 'up',
    openTicker: null,
};

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initControls();
    loadIndex();
});

// ============================================================
// Theme（app.js と同じ）
// ============================================================
function initTheme() {
    const btn = document.getElementById('theme-toggle');
    const updateIcon = () => {
        btn.textContent = document.documentElement.getAttribute('data-theme') === 'light' ? '🌙' : '☀️';
    };
    updateIcon();
    btn.addEventListener('click', () => {
        if (document.documentElement.getAttribute('data-theme') === 'light') {
            document.documentElement.removeAttribute('data-theme');
            localStorage.setItem('theme', 'dark');
        } else {
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem('theme', 'light');
        }
        updateIcon();
    });
}

// ============================================================
// Data
// ============================================================
async function loadIndex() {
    setTbodyMsg('<div class="spinner"></div><div class="loading-txt">履歴を読み込み中...</div>');
    try {
        const r = await fetch('data/history/index.json', { cache: 'no-cache' });
        if (!r.ok) throw new Error(r.status);
        H.index = (await r.json()).snapshots;
        if (H.index.length < 2) {
            setTbodyMsg('<div class="loading-txt">比較できる履歴がまだありません</div>');
            return;
        }
        fillSelects();
        renderHeader();
        H.to = H.index[H.index.length - 1].id;
        applyQuick('prev');
        fetch('data/history/ranks.json', { cache: 'no-cache' })
            .then(r => r.ok ? r.json() : null)
            .then(d => { H.ranks = d; if (H.openTicker) renderTimeline(H.openTicker); })
            .catch(() => {});
    } catch (e) {
        setTbodyMsg('<div class="loading-txt" style="color:var(--dn)">履歴の読み込みに失敗しました</div>');
    }
}

async function getSnap(id) {
    if (!H.cache[id]) {
        const r = await fetch(`data/history/${id}.json`);
        if (!r.ok) throw new Error(r.status);
        const s = await r.json();
        const c = s.cols;
        s.list = s.rows.map(row => Object.fromEntries(c.map((k, i) => [k, row[i]])));
        s.byTicker = Object.fromEntries(s.list.map(x => [x.ticker, x]));
        H.cache[id] = s;
    }
    return H.cache[id];
}

function setTbodyMsg(html) {
    document.getElementById('move-tbody').innerHTML =
        `<tr><td colspan="9"><div class="loading">${html}</div></td></tr>`;
}

// ============================================================
// Header / Selects
// ============================================================
function renderHeader() {
    document.getElementById('stat-snaps').textContent = H.index.length + '回';
    document.getElementById('stat-first').textContent = fmtT(H.index[0].t, true);
    document.getElementById('stat-last').textContent = fmtT(H.index[H.index.length - 1].t);
}

function fillSelects() {
    const opts = [...H.index].reverse()
        .map(s => `<option value="${s.id}">${s.t}（${s.total.toLocaleString()}銘柄）</option>`).join('');
    document.getElementById('sel-from').innerHTML = opts;
    document.getElementById('sel-to').innerHTML = opts;
}

function syncSelects() {
    document.getElementById('sel-from').value = H.from;
    document.getElementById('sel-to').value = H.to;
}

// 比較先から見て「前回」「N日前」のスナップショットを探す
function applyQuick(back) {
    const toIdx = H.index.findIndex(s => s.id === H.to);
    let fromIdx = Math.max(0, toIdx - 1);
    if (back !== 'prev') {
        const target = parseT(H.index[toIdx].t) - Number(back) * 86400000;
        // target 以前で最も新しいもの（なければ最古）
        fromIdx = 0;
        for (let i = toIdx - 1; i >= 0; i--) {
            if (parseT(H.index[i].t) <= target + 3 * 3600000) { fromIdx = i; break; }
        }
    }
    H.from = H.index[fromIdx].id;
    document.querySelectorAll('#quick-pills .pill').forEach(b => b.classList.toggle('active', b.dataset.back === String(back)));
    syncSelects();
    render();
}

// ============================================================
// Controls
// ============================================================
function initControls() {
    document.getElementById('sel-from').addEventListener('change', e => {
        H.from = e.target.value; clearQuick(); render();
    });
    document.getElementById('sel-to').addEventListener('change', e => {
        H.to = e.target.value; clearQuick(); render();
    });
    document.querySelectorAll('#quick-pills .pill').forEach(b =>
        b.addEventListener('click', () => applyQuick(b.dataset.back)));
    bindPills('#market-pills', 'market', v => v);
    bindPills('#scope-pills', 'scope', Number);
    document.querySelectorAll('[data-view]').forEach(b =>
        b.addEventListener('click', () => setView(b.dataset.view)));
    document.getElementById('move-tbody').addEventListener('click', e => {
        const tr = e.target.closest('tr[data-ticker]');
        if (tr) toggleTimeline(tr);
    });
    // グラフのホバー / タップ
    document.getElementById('move-tbody').addEventListener('pointermove', onTimelinePointer);
    document.getElementById('move-tbody').addEventListener('pointerdown', onTimelinePointer);
}

function bindPills(sel, key, conv) {
    document.querySelectorAll(`${sel} .pill`).forEach(b => b.addEventListener('click', () => {
        H[key] = conv(b.dataset[key]);
        document.querySelectorAll(`${sel} .pill`).forEach(x => x.classList.toggle('active', x === b));
        render();
    }));
}

function clearQuick() {
    document.querySelectorAll('#quick-pills .pill').forEach(b => b.classList.remove('active'));
}

function setView(v) {
    H.view = v;
    document.querySelectorAll('#view-pills .pill').forEach(b => b.classList.toggle('active', b.dataset.view === v));
    document.querySelectorAll('.kpi-btn').forEach(b => b.classList.toggle('selected', b.dataset.view === v));
    renderTable();
}

// ============================================================
// Compare
// ============================================================
let RESULT = null;

async function render() {
    if (!H.from || !H.to) return;
    setTbodyMsg('<div class="spinner"></div>');
    let a, b;
    try {
        [b, a] = await Promise.all([getSnap(H.from), getSnap(H.to)]);
    } catch (e) {
        setTbodyMsg('<div class="loading-txt" style="color:var(--dn)">スナップショットの読み込みに失敗しました</div>');
        return;
    }
    RESULT = compare(b, a);
    renderNote(b, a, RESULT.scope);
    renderTable();
}

// b: 比較元, a: 比較先
function compare(b, a) {
    const scope = Math.min(H.scope, a.list.length, b.list.length);
    const inA = a.list.filter(x => x.rank <= scope);
    const inB = b.list.filter(x => x.rank <= scope);
    const bTop = new Set(inB.map(x => x.ticker));
    const aTop = new Set(inA.map(x => x.ticker));

    const rows = { up: [], down: [], new: [], out: [], all: [] };
    for (const x of inA) {
        const prev = b.byTicker[x.ticker];
        const r = { ...x, prev: prev ? prev.rank : null, prevMax: b.list.length, prevScore: prev ? prev.score : null };
        r.delta = prev ? prev.rank - x.rank : null;
        rows.all.push(r);
        if (!bTop.has(x.ticker)) rows.new.push(r);
        else if (r.delta > 0) rows.up.push(r);
        else if (r.delta < 0) rows.down.push(r);
    }
    for (const x of inB) {
        if (aTop.has(x.ticker)) continue;
        const now = a.byTicker[x.ticker];
        rows.out.push({
            ...(now || x), rank: now ? now.rank : null, prev: x.rank, prevScore: x.score,
            curMax: a.list.length, delta: now ? x.rank - now.rank : null, stale: !now,
        });
    }
    rows.up.sort((p, q) => q.delta - p.delta || p.rank - q.rank);
    rows.down.sort((p, q) => p.delta - q.delta || p.rank - q.rank);
    rows.new.sort((p, q) => p.rank - q.rank);
    rows.out.sort((p, q) => p.prev - q.prev);
    return { rows, scope };
}

function renderNote(b, a, scope) {
    const notes = [];
    const ratio = a.total / b.total;
    if (ratio > 1.1 || ratio < 0.9) {
        notes.push(`対象銘柄数が変わっています（${b.total.toLocaleString()} → ${a.total.toLocaleString()}銘柄）。順位変動の一部は対象銘柄の変更によるものです。`);
    }
    if (scope < H.scope) {
        notes.push(`この期間の記録は上位${scope}位までのため、TOP${scope}で比較しています。`);
    }
    if (H.from === H.to) notes.push('比較元と比較先が同じです。');
    if (H.from > H.to) notes.push('比較元のほうが新しい日時になっています。');
    const el = document.getElementById('cmp-note');
    el.hidden = !notes.length;
    el.textContent = notes.join(' ');
}

// ============================================================
// Table
// ============================================================
function renderTable() {
    if (!RESULT) return;
    const { rows } = RESULT;
    const f = x => H.market === 'ALL' || x.market === H.market;

    for (const k of ['up', 'down', 'new', 'out']) {
        document.getElementById('kpi-' + k).textContent = rows[k].filter(f).length;
    }
    document.querySelectorAll('.kpi-btn').forEach(b => b.classList.toggle('selected', b.dataset.view === H.view));

    const list = rows[H.view].filter(f);
    document.getElementById('result-count').textContent = `${list.length} 銘柄`;
    const tbody = document.getElementById('move-tbody');
    if (!list.length) {
        setTbodyMsg('<div class="loading-txt">該当する銘柄はありません</div>');
        return;
    }
    tbody.innerHTML = list.map((x, i) => {
        const grade = getGrade(x.score);
        const open = x.ticker === H.openTicker;
        return `<tr data-ticker="${esc(x.ticker)}" class="clickable${open ? ' open' : ''}" style="animation-delay:${Math.min(i, 30) * 12}ms">
            <td class="r c-rank ${x.rank && x.rank <= 3 ? 'top' : ''}">${x.rank ?? `<span class="c-flat">${x.curMax}位外</span>`}</td>
            <td>${deltaBadge(x)}</td>
            <td class="c-ticker">${esc(x.ticker)}<span class="mkt mkt-${x.market.toLowerCase()}">${x.market}</span></td>
            <td class="c-name" title="${esc(x.name)}">${esc(trunc(x.name, 18))}</td>
            <td class="r c-flat">${x.prev ?? `${x.prevMax}位外`}</td>
            <td class="r c-price">${x.stale ? '<span class="c-flat">—</span>' : fmtPrice(x.price, x.currency)}</td>
            <td class="r ${x.stale ? 'c-flat' : pctCls(x.ret_1m)}">${x.stale ? '—' : fmtPct(x.ret_1m)}</td>
            <td class="r c-score" style="color:${x.stale ? 'var(--txt3)' : gradeColor(grade)}">${x.stale ? '—' : x.score.toFixed(1)}</td>
            <td class="r">${scoreDiff(x)}</td>
        </tr>${open ? timelineRow(x.ticker) : ''}`;
    }).join('');
}

function scoreDiff(x) {
    if (x.stale || x.prevScore == null) return '<span class="c-flat">—</span>';
    const d = x.score - x.prevScore;
    return `<span class="${pctCls(Math.round(d * 10))}">${d > 0 ? '+' : ''}${d.toFixed(1)}</span>`;
}

function deltaBadge(x) {
    if (H.view === 'new' || (x.prev == null)) return '<span class="mv mv-new">NEW</span>';
    if (H.view === 'out' && x.rank == null) return '<span class="mv mv-out">OUT</span>';
    if (x.delta > 0) return `<span class="mv mv-up">▲ ${x.delta}</span>`;
    if (x.delta < 0) return `<span class="mv mv-dn">▼ ${-x.delta}</span>`;
    return '<span class="mv mv-flat">→</span>';
}

// ============================================================
// Score / price timeline
// ============================================================
function toggleTimeline(tr) {
    const t = tr.dataset.ticker;
    H.openTicker = H.openTicker === t ? null : t;
    renderTable();
}

function timelineRow(ticker) {
    return `<tr class="tl-row"><td colspan="9"><div class="tl-box" id="tl-box">${timelineSVG(ticker)}</div></td></tr>`;
}

function renderTimeline(ticker) {
    const box = document.getElementById('tl-box');
    if (box) box.innerHTML = timelineSVG(ticker);
}

// グラフの座標情報（ホバー表示用）
let TL = null;

function timelineSVG(ticker) {
    if (!H.ranks) return '<div class="loading-txt">推移を読み込み中...</div>';
    const pts = H.ranks.ranks[ticker];
    if (!pts || !pts.length) return '<div class="loading-txt">TOP100に入った記録がありません</div>';
    if (pts[0].length < 3) return '<div class="loading-txt">スコアの記録がありません</div>';
    const hasPrice = pts[0].length >= 4;

    const ids = H.ranks.ids;
    const n = ids.length;
    const [name, market] = H.ranks.names[ticker] || [ticker, 'US'];
    const cur = market === 'JP' ? 'JPY' : 'USD';

    // レイアウト: 上段スコア / 下段株価（横軸共通）
    const W = 900, L = 56, R = 40;
    const S = { top: 22, bot: 160 };   // スコア段
    const P = { top: 196, bot: 292 };  // 株価段
    const Ht = hasPrice ? 318 : 188;
    const x = i => L + (n > 1 ? i / (n - 1) : 0.5) * (W - L - R);

    // --- スコア段 ---
    const scores = pts.map(p => p[2]);
    const sHi = Math.max(...scores), sLo = Math.min(...scores);
    const sMax = Math.ceil(Math.max(sHi, 12) * 1.1 / 10) * 10;
    const sMin = Math.min(0, Math.floor(sLo / 10) * 10);
    const ys = v => S.top + (sMax - v) / (sMax - sMin) * (S.bot - S.top);

    let lastLabelY = -Infinity;
    const bands = [['SSS', 60], ['SS', 40], ['S', 25], ['A', 12], ['B', 4]]
        .filter(([, v]) => v <= sMax && v >= sMin)
        .map(([g, v]) => {
            const yy = ys(v);
            const label = yy - lastLabelY >= 12
                ? `<text x="${W - R + 6}" y="${yy + 4}" class="tl-axis" style="fill:${gradeColor(g)}">${g}</text>` : '';
            if (label) lastLabelY = yy;
            return `<line x1="${L}" x2="${W - R}" y1="${yy}" y2="${yy}" class="tl-grade" style="stroke:${gradeColor(g)}"/>${label}`;
        }).join('');
    const sTicks = niceTicks(sMin, sMax).map(v =>
        `<line x1="${L}" x2="${W - R}" y1="${ys(v)}" y2="${ys(v)}" class="tl-grid"/>
         <text x="${L - 6}" y="${ys(v) + 4}" class="tl-axis" text-anchor="end">${v}</text>`).join('');
    const sDots = pts.map(([i, , v]) =>
        `<circle cx="${x(i)}" cy="${ys(v)}" r="${pts.length <= 60 ? 2.6 : 1.6}" style="fill:${gradeColor(getGrade(v))}"/>`).join('');

    // --- 株価段 ---
    let priceSvg = '', yp = null;
    if (hasPrice) {
        const prices = pts.map(p => p[3]);
        const pHi = Math.max(...prices), pLo = Math.min(...prices);
        const pad = (pHi - pLo) * 0.08 || pHi * 0.05;
        const pMax = pHi + pad, pMin = Math.max(0, pLo - pad);
        yp = v => P.top + (pMax - v) / (pMax - pMin) * (P.bot - P.top);
        const pTicks = niceTicks(pMin, pMax, 3).map(v =>
            `<line x1="${L}" x2="${W - R}" y1="${yp(v)}" y2="${yp(v)}" class="tl-grid"/>
             <text x="${L - 6}" y="${yp(v) + 4}" class="tl-axis" text-anchor="end">${fmtAxisPrice(v, cur)}</text>`).join('');
        priceSvg = `
            <text x="${L}" y="${P.top - 8}" class="tl-panel">株価</text>
            ${pTicks}
            <path d="${linePath(pts, x, p => yp(p[3]))}" class="tl-price-line"/>
            ${pts.length <= 60 ? pts.map(p => `<circle cx="${x(p[0])}" cy="${yp(p[3])}" r="2.2" class="tl-price-dot"/>`).join('') : ''}`;
    }

    const selIdx = [H.from, H.to].map(id => ids.indexOf(id)).filter(i => i >= 0);
    const marks = selIdx.map(i =>
        `<line x1="${x(i)}" x2="${x(i)}" y1="${S.top}" y2="${hasPrice ? P.bot : S.bot}" class="tl-mark"/>`).join('');

    TL = { pts, ids, x, ys, yp, cur, W, hasPrice };

    // --- 見出し ---
    const last = pts[pts.length - 1];
    const best = pts.reduce((m, p) => p[2] > m[2] ? p : m);
    const lastGrade = getGrade(last[2]);
    const at = id => { const i = ids.indexOf(id); return pts.find(q => q[0] === i) || null; };
    const pf = at(H.from), pt = at(H.to);
    let period = '';
    if (pf && pt) {
        const ds = pt[2] - pf[2];
        period += `<span class="tl-stat">比較期間スコア <b class="${pctCls(Math.round(ds * 10))}">${ds > 0 ? '+' : ''}${ds.toFixed(1)}</b></span>`;
        if (hasPrice && pf[3] > 0) {
            const dp = (pt[3] / pf[3] - 1) * 100;
            period += `<span class="tl-stat">比較期間株価 <b class="${pctCls(dp)}">${fmtPct(dp)}</b>（${fmtPrice(pf[3], cur)} → ${fmtPrice(pt[3], cur)}）</span>`;
        }
    }

    return `<div class="tl-head">
            <span class="c-ticker">${esc(ticker)}</span>
            <span class="c-name">${esc(name)}</span>
            <span class="tl-stat">直近スコア <b style="color:${gradeColor(lastGrade)}">${last[2].toFixed(1)}</b> <span class="gr gr-${lastGrade.toLowerCase()}">${lastGrade}</span></span>
            ${hasPrice ? `<span class="tl-stat">直近株価 <b>${fmtPrice(last[3], cur)}</b></span>` : ''}
            <span class="tl-stat">最高スコア <b>${best[2].toFixed(1)}</b>（${ids[best[0]].slice(0, 10)}）</span>
            ${period}
        </div>
        <div class="tl-read" id="tl-read">グラフにカーソルを合わせると（スマホはタップ）その回のスコアと株価を表示します</div>
        <svg viewBox="0 0 ${W} ${Ht}" class="tl-svg" id="tl-svg" role="img" aria-label="${esc(ticker)} のスコアと株価の推移">
            <text x="${L}" y="${S.top - 8}" class="tl-panel">スコア</text>
            ${sTicks}${bands}${marks}
            <path d="${linePath(pts, x, p => ys(p[2]))}" class="tl-line"/>
            ${sDots}
            ${priceSvg}
            <line id="tl-cursor" class="tl-cursor" x1="0" x2="0" y1="${S.top}" y2="${hasPrice ? P.bot : S.bot}" visibility="hidden"/>
            <circle id="tl-cur-s" r="4.5" class="tl-cur-dot" visibility="hidden"/>
            ${hasPrice ? '<circle id="tl-cur-p" r="4.5" class="tl-cur-dot tl-cur-price" visibility="hidden"/>' : ''}
            <text x="${L}" y="${Ht - 6}" class="tl-axis">${ids[0].slice(0, 10)}</text>
            <text x="${W - R}" y="${Ht - 6}" class="tl-axis" text-anchor="end">${ids[n - 1].slice(0, 10)}</text>
            <rect x="${L}" y="0" width="${W - L - R}" height="${Ht - 20}" fill="transparent" class="tl-hit"/>
        </svg>`;
}

// 連続する回だけ線でつなぐ（TOP100圏外の回で途切れる）
function linePath(pts, x, yOf) {
    let d = '', prev = -2;
    for (const p of pts) {
        d += (p[0] === prev + 1 ? 'L' : 'M') + x(p[0]).toFixed(1) + ' ' + yOf(p).toFixed(1);
        prev = p[0];
    }
    return d;
}

// ホバー / タップで、その回のスコアと株価を表示
function onTimelinePointer(e) {
    const svg = e.target.closest('#tl-svg');
    if (!svg || !TL) return;
    const rect = svg.getBoundingClientRect();
    const sx = (e.clientX - rect.left) / rect.width * TL.W;
    let best = null, bd = Infinity;
    for (const p of TL.pts) {
        const d = Math.abs(TL.x(p[0]) - sx);
        if (d < bd) { bd = d; best = p; }
    }
    if (!best) return;
    const cx = TL.x(best[0]);
    const set = (id, attrs) => {
        const el = document.getElementById(id);
        if (el) for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
    };
    const g = getGrade(best[2]);
    set('tl-cursor', { x1: cx, x2: cx, visibility: 'visible' });
    set('tl-cur-s', { cx, cy: TL.ys(best[2]), visibility: 'visible', style: `fill:${gradeColor(g)}` });
    if (TL.hasPrice) set('tl-cur-p', { cx, cy: TL.yp(best[3]), visibility: 'visible' });
    const t = TL.ids[best[0]];
    document.getElementById('tl-read').innerHTML =
        `<b>${t.slice(0, 10)} ${t.slice(11, 13)}:${t.slice(13, 15)}</b>
         　スコア <b style="color:${gradeColor(g)}">${best[2].toFixed(1)}</b> <span class="gr gr-${g.toLowerCase()}">${g}</span>
         ${TL.hasPrice ? `　株価 <b>${fmtPrice(best[3], TL.cur)}</b>` : ''}`;
}

function niceTicks(lo, hi, count = 4) {
    const span = hi - lo;
    if (!(span > 0)) return [lo];
    const raw = span / count;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    const step = [1, 2, 2.5, 5, 10].map(m => m * mag).find(s => s >= raw);
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(+v.toFixed(6));
    return out;
}

function fmtAxisPrice(v, c) {
    if (c === 'JPY') return '¥' + (v >= 10000 ? +(v / 10000).toFixed(1) + '万' : Math.round(v).toLocaleString());
    return '$' + (v >= 1000 ? Math.round(v).toLocaleString() : v >= 10 ? v.toFixed(0) : v.toFixed(2));
}

// ============================================================
// Helpers（app.js と同じ）
// ============================================================
function parseT(t) { return new Date(t.replace(' ', 'T') + ':00+09:00').getTime(); }
function fmtT(t, dateOnly) {
    const [d, hm] = t.split(' ');
    const [, m, day] = d.split('-').map(Number);
    return dateOnly ? `${d.slice(0, 4)}/${m}/${day}` : `${m}/${day} ${hm}`;
}
function fmtPrice(p, c) { return c === 'JPY' ? '¥' + Math.round(p).toLocaleString() : '$' + p.toFixed(2); }
function fmtPct(v) { return (v > 0 ? '+' : '') + v.toFixed(1) + '%'; }
function pctCls(v) { return v > 0 ? 'c-up' : v < 0 ? 'c-dn' : 'c-flat'; }
function getGrade(s) {
    if (s >= 60) return 'SSS'; if (s >= 40) return 'SS'; if (s >= 25) return 'S';
    if (s >= 12) return 'A'; if (s >= 4) return 'B'; return 'C';
}
function gradeColor(g) {
    return { SSS:'#ff3b5c', SS:'#ff7b3a', S:'#fbbf24', A:'#3fb950', B:'#60a5fa', C:'#484f58' }[g] || '#484f58';
}
function trunc(s, n) { return !s ? '' : s.length > n ? s.slice(0, n) + '…' : s; }
function esc(s) {
    return String(s ?? '').replace(/[&<>"']/g, c => ({ '&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;' }[c]));
}

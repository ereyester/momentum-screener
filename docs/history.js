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
// Rank timeline
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

function timelineSVG(ticker) {
    if (!H.ranks) return '<div class="loading-txt">スコア推移を読み込み中...</div>';
    const pts = H.ranks.ranks[ticker];
    if (!pts || !pts.length) return '<div class="loading-txt">TOP100に入った記録がありません</div>';
    if (pts[0].length < 3) return '<div class="loading-txt">スコアの記録がありません</div>';

    const ids = H.ranks.ids;
    const n = ids.length;
    const W = 900, Ht = 190, L = 40, R = 40, T = 12, B = 26;
    const scores = pts.map(p => p[2]);
    const hi = Math.max(...scores), lo = Math.min(...scores);
    // 縦軸: 0〜最高値（グレード境界が見える範囲）に少し余白
    const yMax = Math.ceil(Math.max(hi, 12) * 1.1 / 10) * 10;
    const yMin = Math.min(0, Math.floor(lo / 10) * 10);
    const x = i => L + (n > 1 ? i / (n - 1) : 0.5) * (W - L - R);
    const y = v => T + (yMax - v) / (yMax - yMin) * (Ht - T - B);

    // 連続する回だけ線でつなぐ（TOP100圏外の回で途切れる）
    let path = '', prev = -2;
    for (const [i, , v] of pts) {
        path += (i === prev + 1 ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1);
        prev = i;
    }
    // グレード境界線
    const bands = [['SSS', 60], ['SS', 40], ['S', 25], ['A', 12], ['B', 4]]
        .filter(([, v]) => v <= yMax && v >= yMin)
        .map(([g, v]) => `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="tl-grade" style="stroke:${gradeColor(g)}"/>
            <text x="${W - R + 6}" y="${y(v) + 4}" class="tl-axis" style="fill:${gradeColor(g)}">${g}</text>`).join('');
    const ticks = niceTicks(yMin, yMax).map(v =>
        `<line x1="${L}" x2="${W - R}" y1="${y(v)}" y2="${y(v)}" class="tl-grid"/>
         <text x="${L - 6}" y="${y(v) + 4}" class="tl-axis" text-anchor="end">${v}</text>`).join('');
    const selIdx = [H.from, H.to].map(id => ids.indexOf(id)).filter(i => i >= 0);
    const marks = selIdx.map(i => `<line x1="${x(i)}" x2="${x(i)}" y1="${T}" y2="${Ht - B}" class="tl-mark"/>`).join('');
    const dots = pts.map(([i, r, v]) =>
        `<circle cx="${x(i)}" cy="${y(v)}" r="${pts.length <= 60 ? 2.6 : 1.6}" class="tl-dot" style="fill:${gradeColor(getGrade(v))}"><title>${ids[i].replace('_', ' ')}: スコア ${v.toFixed(1)}（${r}位）</title></circle>`).join('');

    const last = pts[pts.length - 1];
    const best = pts.reduce((m, p) => p[2] > m[2] ? p : m);
    const [name] = H.ranks.names[ticker] || [ticker];
    const lastGrade = getGrade(last[2]);

    // 比較期間のスコア変化（両方の回に記録がある場合）
    const at = id => { const i = ids.indexOf(id); const p = pts.find(q => q[0] === i); return p ? p[2] : null; };
    const sf = at(H.from), st = at(H.to);
    const period = sf != null && st != null
        ? `<span class="tl-stat">比較期間 <b class="${pctCls(Math.round((st - sf) * 10))}">${st - sf > 0 ? '+' : ''}${(st - sf).toFixed(1)}</b>（${sf.toFixed(1)} → ${st.toFixed(1)}）</span>`
        : '';

    return `<div class="tl-head">
            <span class="c-ticker">${esc(ticker)}</span>
            <span class="c-name">${esc(name)}</span>
            <span class="tl-stat">直近 <b style="color:${gradeColor(lastGrade)}">${last[2].toFixed(1)}</b> <span class="gr gr-${lastGrade.toLowerCase()}">${lastGrade}</span>（${ids[last[0]].slice(0, 10)}・${last[1]}位）</span>
            <span class="tl-stat">最高 <b>${best[2].toFixed(1)}</b>（${ids[best[0]].slice(0, 10)}）</span>
            ${period}
        </div>
        <svg viewBox="0 0 ${W} ${Ht}" class="tl-svg" role="img" aria-label="${esc(ticker)} のスコア推移">
            ${ticks}${bands}${marks}
            <path d="${path}" class="tl-line"/>
            ${dots}
            <text x="${L}" y="${Ht - 6}" class="tl-axis">${ids[0].slice(0, 10)}</text>
            <text x="${W - R}" y="${Ht - 6}" class="tl-axis" text-anchor="end">${ids[n - 1].slice(0, 10)}</text>
        </svg>`;
}

function niceTicks(lo, hi) {
    const span = hi - lo;
    const step = span <= 40 ? 10 : span <= 100 ? 20 : span <= 200 ? 50 : 100;
    const out = [];
    for (let v = Math.ceil(lo / step) * step; v <= hi; v += step) out.push(v);
    return out;
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

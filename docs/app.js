/**
 * モメンタムチンパン — Redesigned Frontend
 */

let DATA = null;
let marketFilter = 'ALL';
let sort = { key: 'score', dir: 'desc' };

document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initTabs();
    initFilters();
    initSort();
    loadData();
});

// ============================================================
// Theme
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
async function loadData() {
    document.getElementById('ranking-tbody').innerHTML =
        '<tr><td colspan="11"><div class="loading"><div class="spinner"></div><div class="loading-txt">データ読み込み中...</div></div></td></tr>';
    try {
        const r = await fetch('data/latest.json');
        if (!r.ok) throw new Error(r.status);
        DATA = await r.json();
        render();
    } catch (e) {
        document.getElementById('ranking-tbody').innerHTML =
            '<tr><td colspan="11"><div class="loading"><div class="loading-txt" style="color:var(--dn)">データの読み込みに失敗しました</div></div></td></tr>';
    }
}

function render() {
    renderHeader();
    renderPodium();
    renderRanking();
    renderDeck();
}

// ============================================================
// Header
// ============================================================
function renderHeader() {
    document.getElementById('stat-total').textContent = DATA.total_scanned.toLocaleString();
    document.getElementById('stat-usdjpy').textContent = '¥' + DATA.usdjpy.toFixed(2);
    const d = new Date(DATA.updated_at.replace(' ', 'T'));
    document.getElementById('stat-updated').textContent =
        `${(d.getMonth()+1)}/${d.getDate()} ${d.getHours()}:${String(d.getMinutes()).padStart(2,'0')}`;
}

// ============================================================
// Podium (Top 3 Cards)
// ============================================================
function renderPodium() {
    const top3 = DATA.ranking.slice(0, 3);
    const styles = ['gold', 'silver', 'bronze'];
    const medals = ['🥇', '🥈', '🥉'];
    const container = document.getElementById('podium-cards');
    container.innerHTML = '';

    top3.forEach((item, i) => {
        const grade = getGrade(item.score);
        const card = document.createElement('div');
        card.className = `pod-card ${styles[i]}`;
        card.innerHTML = `
            <div class="pod-rank">${medals[i]}</div>
            <div class="pod-ticker">${item.ticker} <span class="mkt mkt-${item.market.toLowerCase()}">${item.market}</span></div>
            <div class="pod-name">${item.name}</div>
            <div class="pod-price">${fmtPrice(item.price, item.currency)}</div>
            <div class="pod-metrics">
                <div class="pod-metric">
                    <span class="pod-metric-label">本日</span>
                    <span class="pod-metric-value ${pctCls(item.day_chg)}">${fmtPct(item.day_chg)}</span>
                </div>
                <div class="pod-metric">
                    <span class="pod-metric-label">1ヶ月</span>
                    <span class="pod-metric-value ${pctCls(item.ret_1m)}">${fmtPct(item.ret_1m)}</span>
                </div>
                <div class="pod-metric">
                    <span class="pod-metric-label">3ヶ月</span>
                    <span class="pod-metric-value ${pctCls(item.ret_3m)}">${fmtPct(item.ret_3m)}</span>
                </div>
                <div class="pod-metric">
                    <span class="pod-metric-label">年初来</span>
                    <span class="pod-metric-value ${pctCls(item.ytd_chg)}">${fmtPct(item.ytd_chg)}</span>
                </div>
            </div>
            <div class="pod-score-row">
                <span class="pod-score" style="color:${gradeColor(grade)}">${item.score.toFixed(1)}</span>
                <span class="gr gr-${grade.toLowerCase()}">${grade}</span>
            </div>
        `;
        container.appendChild(card);
    });
}

// ============================================================
// Tabs
// ============================================================
function initTabs() {
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            btn.classList.add('active');
            document.getElementById('tab-' + btn.dataset.tab).classList.add('active');
        });
    });
}

// ============================================================
// Filters
// ============================================================
function initFilters() {
    document.querySelectorAll('.pill').forEach(btn => {
        btn.addEventListener('click', () => {
            marketFilter = btn.dataset.market;
            document.querySelectorAll('.pill').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            renderRanking();
        });
    });
}

// ============================================================
// Sort
// ============================================================
function initSort() {
    document.querySelectorAll('#ranking-table th.sortable').forEach(th => {
        th.addEventListener('click', () => {
            const key = th.dataset.sort;
            if (sort.key === key) sort.dir = sort.dir === 'desc' ? 'asc' : 'desc';
            else { sort.key = key; sort.dir = 'desc'; }
            updateSortUI();
            renderRanking();
        });
    });
}

function updateSortUI() {
    document.querySelectorAll('#ranking-table th.sortable').forEach(th => {
        th.classList.remove('sort-asc', 'sort-desc');
        if (th.dataset.sort === sort.key) th.classList.add(sort.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    });
}

// ============================================================
// Ranking Table
// ============================================================
function renderRanking() {
    if (!DATA) return;
    let rows = [...DATA.ranking];

    if (marketFilter !== 'ALL') rows = rows.filter(r => r.market === marketFilter);

    rows.sort((a, b) => {
        let va = a[sort.key], vb = b[sort.key];
        if (typeof va === 'string') return sort.dir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
        return sort.dir === 'asc' ? va - vb : vb - va;
    });

    document.getElementById('result-count').textContent = rows.length + ' 銘柄';
    const maxScore = Math.max(...rows.map(r => Math.abs(r.score)), 1);
    const tbody = document.getElementById('ranking-tbody');
    tbody.innerHTML = '';

    rows.forEach((item, idx) => {
        const tr = document.createElement('tr');
        tr.style.animationDelay = `${Math.min(idx * 15, 300)}ms`;
        const grade = getGrade(item.score);
        const barW = Math.min(Math.abs(item.score) / maxScore * 100, 100);

        tr.innerHTML = `
            <td class="c-rank ${idx < 3 ? 'top' : ''}">${idx + 1}</td>
            <td class="c-ticker">${item.ticker}<span class="mkt mkt-${item.market.toLowerCase()}">${item.market}</span></td>
            <td class="c-name" title="${item.name}">${trunc(item.name, 16)}</td>
            <td class="r c-price">${fmtPrice(item.price, item.currency)}</td>
            <td class="r ${pctCls(item.day_chg)}">${fmtPct(item.day_chg)}</td>
            <td class="r ${pctCls(item.ret_1m)}">${fmtPct(item.ret_1m)}</td>
            <td class="r ${pctCls(item.ret_3m)}">${fmtPct(item.ret_3m)}</td>
            <td class="r ${pctCls(item.ytd_chg)}">${fmtPct(item.ytd_chg)}</td>
            <td class="r c-rsi" style="color:${rsiColor(item.rsi)}">${item.rsi.toFixed(0)}</td>
            <td class="r c-score" style="color:${gradeColor(grade)}">
                ${item.score.toFixed(1)}
                <span class="score-bg" style="width:${barW}%;background:${gradeColor(grade)}"></span>
            </td>
            <td><span class="gr gr-${grade.toLowerCase()}">${grade}</span></td>
        `;
        tbody.appendChild(tr);
    });
    updateSortUI();
}

// ============================================================
// Deck
// ============================================================
function renderDeck() {
    if (!DATA?.deck) return;
    updateDeckUI(DATA.deck.budget_man);

    // Initial setup of budget input
    const budgetInput = document.getElementById('budget-input');
    budgetInput.value = DATA.deck.budget_man;
    
    // Listen for changes
    budgetInput.addEventListener('input', (e) => {
        const val = parseInt(e.target.value);
        if (!isNaN(val) && val > 0) {
            updateDeckUI(val);
        }
    });
}

function updateDeckUI(budgetMan) {
    const dk = DATA.deck;
    const budgetJpy = budgetMan * 10000;
    const nStocks = dk.stocks.length;
    const targetJpyPerStock = nStocks > 0 ? budgetJpy / nStocks : 0;
    
    let totalAllocMan = 0;
    
    // First pass: Allocate evenly based on targetJpyPerStock
    const computedStocks = dk.stocks.map(item => {
        let shares = 0;
        let entryJpy = item.currency === 'JPY' ? item.entry_price : item.entry_price * DATA.usdjpy;
        let lotSize = item.currency === 'JPY' ? 100 : 1;
        let costPerLot = entryJpy * lotSize;

        if (targetJpyPerStock >= costPerLot) {
            const lots = Math.floor(targetJpyPerStock / costPerLot);
            shares = lots * lotSize;
        }
        
        return {
            ...item,
            _entryJpy: entryJpy,
            _lotSize: lotSize,
            _costPerLot: costPerLot,
            shares: shares
        };
    });

    // Calculate remaining budget after first pass
    let currentUsedJpy = computedStocks.reduce((sum, item) => sum + (item.shares * item._entryJpy), 0);
    let remainingJpy = budgetJpy - currentUsedJpy;

    // Second pass: Greedy allocation with leftover budget (prioritize higher score stocks)
    // Stocks are already sorted by score in deck, so we just iterate top to bottom
    let keepAllocating = true;
    while (keepAllocating && remainingJpy > 0) {
        keepAllocating = false;
        for (let i = 0; i < computedStocks.length; i++) {
            let item = computedStocks[i];
            if (remainingJpy >= item._costPerLot) {
                item.shares += item._lotSize;
                remainingJpy -= item._costPerLot;
                keepAllocating = true;
            }
        }
    }

    // Finalize allocations
    computedStocks.forEach(item => {
        const costJpy = item.shares * item._entryJpy;
        item.alloc_man = Math.round(costJpy / 10000);
        totalAllocMan += item.alloc_man;
    });
    
    // Update summary KPIs
    document.getElementById('deck-total-alloc').textContent = totalAllocMan.toLocaleString() + '万円';
    document.getElementById('deck-remaining').textContent = (budgetMan - totalAllocMan).toLocaleString() + '万円';
    document.getElementById('deck-max-loss').textContent = '-' + Math.round(totalAllocMan * 0.07).toLocaleString() + '万円';

    // Update cards
    const container = document.getElementById('deck-cards');
    container.innerHTML = '';

    computedStocks.forEach((item, idx) => {
        const grade = getGrade(item.score);
        const card = document.createElement('div');
        const isExcluded = item.shares === 0;
        card.className = `dk-card ${isExcluded ? 'excluded' : ''}`;
        card.style.animationDelay = `${idx * 30}ms`;
        card.style.animation = 'fadeUp .3s ease backwards';
        
        const allocValue = isExcluded ? '<span style="color:var(--dn);font-size:.7rem">予算不足</span>' : `${item.alloc_man.toLocaleString()}万円`;
        
        card.innerHTML = `
            <div class="dk-head">
                <div>
                    <div class="dk-ticker">${item.ticker} <span class="mkt mkt-${item.market.toLowerCase()}">${item.market}</span></div>
                    <div class="dk-name">${item.name}</div>
                </div>
                <div class="dk-score-badge">
                    <span style="font-size:1.1rem;font-weight:800;color:${gradeColor(grade)}">${item.score.toFixed(1)}</span>
                    <span class="gr gr-${grade.toLowerCase()}">${grade}</span>
                </div>
            </div>
            <div class="dk-grid">
                <div class="dk-item">
                    <span class="dk-item-label">現在値</span>
                    <span class="dk-item-value">${fmtPrice(item.price, item.currency)}</span>
                </div>
                <div class="dk-item">
                    <span class="dk-item-label">株数</span>
                    <span class="dk-item-value">${item.shares.toLocaleString()}株</span>
                </div>
                <div class="dk-item">
                    <span class="dk-item-label">1ヶ月</span>
                    <span class="dk-item-value ${pctCls(item.ret_1m)}">${fmtPct(item.ret_1m)}</span>
                </div>
                <div class="dk-item">
                    <span class="dk-item-label">配分</span>
                    <span class="dk-item-value" style="font-weight:800">${allocValue}</span>
                </div>
            </div>
            <div class="dk-action">
                <div class="dk-action-item">
                    <div class="dk-action-label">指値</div>
                    <div class="dk-action-value dk-entry">${fmtPrice(item.entry_price, item.currency)}</div>
                </div>
                <div class="dk-action-item">
                    <div class="dk-action-label">損切</div>
                    <div class="dk-action-value dk-stop">${fmtPrice(item.stop_price, item.currency)}</div>
                </div>
                <div class="dk-action-item">
                    <div class="dk-action-label">目標</div>
                    <div class="dk-action-value dk-target">${fmtPrice(item.target_price, item.currency)}</div>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

// ============================================================
// Helpers
// ============================================================
function fmtPrice(p, c) { return c === 'JPY' ? '¥' + Math.round(p).toLocaleString() : '$' + p.toFixed(2); }
function fmtPct(v) { return (v > 0 ? '+' : '') + v.toFixed(1) + '%'; }
function pctCls(v) { return v > 0 ? 'c-up' : v < 0 ? 'c-dn' : 'c-flat'; }
function rsiColor(r) {
    if (r >= 70) return '#f85149';
    if (r >= 60) return '#fbbf24';
    if (r >= 40) return '#8b949e';
    return '#60a5fa';
}
function getGrade(s) {
    if (s >= 60) return 'SSS'; if (s >= 40) return 'SS'; if (s >= 25) return 'S';
    if (s >= 12) return 'A'; if (s >= 4) return 'B'; return 'C';
}
function gradeColor(g) {
    return { SSS:'#ff3b5c', SS:'#ff7b3a', S:'#fbbf24', A:'#3fb950', B:'#60a5fa', C:'#484f58' }[g] || '#484f58';
}
function trunc(s, n) { return !s ? '' : s.length > n ? s.slice(0, n) + '…' : s; }

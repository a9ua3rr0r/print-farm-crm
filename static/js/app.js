let telemetryViewer = null;
let overviewViewer = null;
let currentTelemetryPrinterId = null;
let telemetryChangedFlag = false;

// ============================================================================
// 1. УПРАВЛЕНИЕ ТЕМОЙ ОФОРМЛЕНИЯ (DARK SLATE / CLEAN LIGHT)
// ============================================================================
function getSavedTheme() {
    return localStorage.getItem('printfarm_theme') || 'dark';
}

function applyTheme(theme) {
    document.documentElement.setAttribute('data-bs-theme', theme);
    localStorage.setItem('printfarm_theme', theme);

    const iconEl = document.getElementById('theme-toggle-icon');
    const textEl = document.getElementById('theme-toggle-text');
    if (iconEl) {
        iconEl.className = (theme === 'light')
            ? 'bi bi-moon-stars-fill text-primary'
            : 'bi bi-sun-fill text-warning';
    }
    if (textEl) {
        textEl.textContent = (theme === 'light') ? 'Тёмная тема' : 'Светлая тема';
    }

    if (overviewViewer) overviewViewer.applyThemeColors(theme);
    if (telemetryViewer) telemetryViewer.applyThemeColors(theme);
}

function toggleAppTheme() {
    const current = document.documentElement.getAttribute('data-bs-theme') || 'dark';
    const next = (current === 'dark') ? 'light' : 'dark';
    applyTheme(next);
}

// ============================================================================
// 2. АВТОПОДСТАНОВКА ЗАКРЕПЛЁННЫХ ЦЕН ИЗ GOOGLE ТАБЛИЦЫ НА СКЛАДЕ
// ============================================================================
function onMarketplaceCatalogSelect(selectEl) {
    const opt = selectEl.options[selectEl.selectedIndex];
    if (!opt) return;

    const materialInput = document.getElementById('spool-material-input');
    const colorInput = document.getElementById('spool-color-input');
    const weightInput = document.getElementById('spool-weight-input');
    const priceDisplay = document.getElementById('spool-price-display');
    const skuDisplay = document.getElementById('spool-sku-display');

    if (materialInput && opt.dataset.material) materialInput.value = opt.dataset.material;
    if (colorInput && opt.dataset.color) colorInput.value = opt.dataset.color;
    if (weightInput && opt.dataset.weight) weightInput.value = opt.dataset.weight;
    if (priceDisplay && opt.dataset.price) priceDisplay.value = `${opt.dataset.price} ₽ (из таблицы)`;
    if (skuDisplay && opt.dataset.sku) skuDisplay.value = opt.dataset.sku;
}

// ============================================================================
// 3. ЖИВОЙ КАЛЬКУЛЯТОР СЕБЕСТОИМОСТИ И МАРЖИ ЗАКАЗА
// ============================================================================
function calculateOrderEconomics() {
    const rows = document.querySelectorAll('#items-container .item-row');
    if (!rows.length) return;

    let totalCost = 0;
    let totalRevenue = 0;

    rows.forEach(row => {
        const sel = row.querySelector('select');
        const qtyInput = row.querySelector('input[type="number"]');
        if (!sel || !qtyInput) return;

        const opt = sel.options[sel.selectedIndex];
        if (!opt) return;

        const price = parseFloat(opt.dataset.price || '0');
        const weightG = parseFloat(opt.dataset.weight || '50');
        const timeMin = parseFloat(opt.dataset.time || '60');
        const qty = Math.max(1, parseInt(qtyInput.value || '1'));

        const hours = timeMin / 60.0;
        const filamentCost = weightG * 2.15 * qty;
        const electricityCost = hours * 0.35 * 7.50 * qty;
        const amortizationCost = hours * 35.0 * qty;
        const scrapReserve = filamentCost * 0.05;

        totalCost += (filamentCost + electricityCost + amortizationCost + scrapReserve);
        totalRevenue += (price * qty);
    });

    const profit = totalRevenue - totalCost;
    const margin = totalRevenue > 0 ? ((profit / totalRevenue) * 100.0) : 0;

    const costEl = document.getElementById('calc-order-cost');
    const revEl = document.getElementById('calc-order-revenue');
    const profEl = document.getElementById('calc-order-profit');
    const margEl = document.getElementById('calc-order-margin');

    if (costEl) costEl.textContent = `${totalCost.toFixed(0)} ₽`;
    if (revEl) revEl.textContent = `${totalRevenue.toFixed(0)} ₽`;
    if (profEl) profEl.textContent = `${profit.toFixed(0)} ₽`;
    if (margEl) margEl.textContent = `${margin.toFixed(1)}%`;
}

// ============================================================================
// 4. ИНИЦИАЛИЗАЦИЯ СТРАНИЦЫ И ФИЛЬТРОВ
// ============================================================================
function ensureThreeJsLoaded() {
    return new Promise((resolve) => {
        if (typeof THREE !== 'undefined') {
            resolve();
            return;
        }
        const script = document.createElement('script');
        script.src = 'https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js';
        script.onload = () => resolve();
        document.head.appendChild(script);
    });
}

document.addEventListener('DOMContentLoaded', async () => {
    applyTheme(getSavedTheme());

    const catalogSelect = document.getElementById('spool-catalog-select');
    if (catalogSelect) onMarketplaceCatalogSelect(catalogSelect);

    if (document.getElementById('calc-order-cost')) {
        calculateOrderEconomics();
    }

    const simBtn = document.getElementById('btn-sim-tick');
    if (simBtn) {
        simBtn.addEventListener('click', async () => {
            simBtn.disabled = true;
            const origHtml = simBtn.innerHTML;
            simBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Печать (+20%)...';
            try {
                const res = await fetch('/api/simulator/tick', { method: 'POST' });
                if (res.ok) {
                    window.location.reload();
                } else {
                    simBtn.disabled = false;
                    simBtn.innerHTML = origHtml;
                }
            } catch (err) {
                console.error(err);
                simBtn.disabled = false;
                simBtn.innerHTML = origHtml;
            }
        });
    }

    const autoSwitch = document.getElementById('switch-sim-auto');
    if (autoSwitch) {
        autoSwitch.addEventListener('change', async () => {
            try {
                const res = await fetch('/api/simulator/toggle', { method: 'POST' });
                const data = await res.json();
                const badge = document.getElementById('badge-sim-mode');
                if (badge) {
                    badge.textContent = data.auto_enabled ? 'АВТО ВКЛ' : 'РУЧНОЙ';
                    badge.className = data.auto_enabled
                        ? 'badge bg-success text-white'
                        : 'badge bg-warning text-dark';
                }
            } catch (err) {
                console.error(err);
            }
        });
    }

    await ensureThreeJsLoaded();

    const telModalEl = document.getElementById('printerTelemetryModal');
    if (telModalEl) {
        telModalEl.addEventListener('shown.bs.modal', () => {
            if (telemetryViewer) telemetryViewer.resize();
        });
        telModalEl.addEventListener('hidden.bs.modal', () => {
            if (telemetryChangedFlag) window.location.reload();
        });
    }

    const overviewContainer = document.getElementById('farm3d-canvas-container');
    if (overviewContainer && typeof THREE !== 'undefined') {
        initOverviewPrintBed3D(overviewContainer);
    }

    const savedView = localStorage.getItem('printfarm_printers_view') || 'cards';
    if (document.getElementById('view-cards') && document.getElementById('view-rack')) {
        switchPrintersView(savedView);
    }

    // Инициализация деликатного 3D-наклона карточек с живым бликом
    initInteractiveCardTilt('.tilt-card', 3.0);
});

// ============================================================================
// ИНТЕРАКТИВНЫЙ 3D-НАКЛОН И ДИНАМИЧЕСКИЙ БЛИК КАРТОЧЕК (TILT & SHEEN)
// Адаптирован под темную (Obsidian Ruby) и светлую (Alabaster Carmine) темы
// ============================================================================
function initInteractiveCardTilt(selector = '.tilt-card', maxAngle = 3.6) {
    const cards = document.querySelectorAll(selector);
    cards.forEach(card => {
        let sheen = card.querySelector('.card-sheen-layer');
        if (!sheen) {
            sheen = document.createElement('div');
            sheen.className = 'card-sheen-layer';
            card.appendChild(sheen);
        }

        let isHovered = false;
        let curX = 0, curY = 0;
        let targetX = 0, targetY = 0;
        let animId = null;

        const applySheen = (px, py) => {
            const isLight = document.documentElement.getAttribute('data-bs-theme') === 'light';
            if (isLight) {
                // На светлой теме: сочный, элегантный карминово-рубиновый блик с мягким контрастным ореолом Fresnel
                sheen.style.background = `radial-gradient(circle 320px at ${px}px ${py}px, rgba(190, 18, 60, 0.25) 0%, rgba(225, 29, 72, 0.15) 28%, rgba(251, 113, 133, 0.07) 50%, rgba(20, 18, 26, 0.04) 72%, transparent 100%)`;
            } else {
                // На темной теме: кристаллический белый блик с рубиновым свечением
                sheen.style.background = `radial-gradient(circle 320px at ${px}px ${py}px, rgba(255, 255, 255, 0.18) 0%, rgba(225, 29, 72, 0.12) 32%, rgba(225, 29, 72, 0.03) 58%, transparent 75%)`;
            }
        };

        const update = () => {
            curX += (targetX - curX) * 0.12;
            curY += (targetY - curY) * 0.12;
            card.style.transform = `perspective(1000px) rotateX(${curX.toFixed(2)}deg) rotateY(${curY.toFixed(2)}deg)`;

            const isLight = document.documentElement.getAttribute('data-bs-theme') === 'light';
            const shadowX = (-curY * 1.8).toFixed(1);
            const shadowY = (curX * 1.8 + 8).toFixed(1);

            if (isLight) {
                card.style.boxShadow = `${shadowX}px ${shadowY}px 24px rgba(190, 18, 60, 0.18), 0 3px 8px rgba(20, 18, 26, 0.08)`;
                card.style.borderColor = '#be123c';
            } else {
                card.style.boxShadow = `${shadowX}px ${shadowY}px 30px rgba(0, 0, 0, 0.65), 0 0 22px rgba(225, 29, 72, 0.22)`;
                card.style.borderColor = 'rgba(225, 29, 72, 0.55)';
            }

            if (isHovered || Math.abs(curX) > 0.05 || Math.abs(curY) > 0.05) {
                animId = requestAnimationFrame(update);
            } else {
                card.style.transform = '';
                card.style.boxShadow = '';
                card.style.borderColor = '';
                animId = null;
            }
        };

        card.addEventListener('mouseenter', (e) => {
            isHovered = true;
            const rect = card.getBoundingClientRect();
            const px = e.clientX - rect.left;
            const py = e.clientY - rect.top;
            applySheen(px, py);
            sheen.style.opacity = '1';
            if (!animId) animId = requestAnimationFrame(update);
        });

        card.addEventListener('mousemove', (e) => {
            const rect = card.getBoundingClientRect();
            const x = (e.clientX - rect.left) / rect.width - 0.5;
            const y = (e.clientY - rect.top) / rect.height - 0.5;
            targetX = -y * maxAngle * 2;
            targetY = x * maxAngle * 2;

            const px = e.clientX - rect.left;
            const py = e.clientY - rect.top;
            applySheen(px, py);
            sheen.style.opacity = '1';
        });

        card.addEventListener('mouseleave', () => {
            isHovered = false;
            targetX = 0;
            targetY = 0;
            sheen.style.opacity = '0';
        });
    });
}

function filterPrinters(status, btn) {
    if (btn) {
        const group = btn.closest('.printer-filter-group');
        if (group) {
            group.querySelectorAll('.btn').forEach(b => {
                b.classList.remove('btn-primary', 'active');
                b.classList.add('btn-outline-secondary', 'text-light');
            });
        }
        btn.classList.remove('btn-outline-secondary', 'text-light');
        btn.classList.add('btn-primary', 'active');
    }

    const items = document.querySelectorAll('.printer-filter-item');
    let visibleCount = 0;
    items.forEach(item => {
        const itemStatus = item.getAttribute('data-status');
        if (status === 'all' || itemStatus === status) {
            item.classList.remove('d-none');
            visibleCount++;
        } else {
            item.classList.add('d-none');
        }
    });

    const emptyNotice = document.getElementById('printers-filter-empty');
    if (emptyNotice) {
        emptyNotice.classList.toggle('d-none', visibleCount > 0);
    }
}

function switchPrintersView(mode) {
    const cardsBlock = document.getElementById('view-cards');
    const rackBlock = document.getElementById('view-rack');
    const btnCards = document.getElementById('btn-view-cards');
    const btnRack = document.getElementById('btn-view-rack');

    if (!cardsBlock || !rackBlock) return;
    localStorage.setItem('printfarm_printers_view', mode);

    if (mode === 'rack') {
        cardsBlock.classList.add('d-none');
        rackBlock.classList.remove('d-none');
        if (btnRack && btnCards) {
            btnRack.className = 'btn btn-sm btn-primary';
            btnCards.className = 'btn btn-sm btn-outline-secondary text-light';
        }
    } else {
        rackBlock.classList.add('d-none');
        cardsBlock.classList.remove('d-none');
        if (btnRack && btnCards) {
            btnCards.className = 'btn btn-sm btn-primary';
            btnRack.className = 'btn btn-sm btn-outline-secondary text-light';
        }
    }
}

function addOrderItemRow() {
    const container = document.getElementById('items-container');
    if (!container) return;
    const firstRow = container.querySelector('.item-row');
    if (!firstRow) return;

    const clone = firstRow.cloneNode(true);
    clone.querySelector('select').selectedIndex = 0;
    clone.querySelector('input[type="number"]').value = 1;
    container.appendChild(clone);
    calculateOrderEconomics();
}

function removeOrderItemRow(btn) {
    const rows = document.querySelectorAll('#items-container .item-row');
    if (rows.length > 1) {
        btn.closest('.item-row').remove();
        calculateOrderEconomics();
    }
}

function copyTrackLink(url, btn) {
    const fullUrl = window.location.origin + url;
    navigator.clipboard.writeText(fullUrl).then(() => {
        const oldHtml = btn.innerHTML;
        btn.innerHTML = '<i class="bi bi-check2 text-success"></i> Скопировано';
        setTimeout(() => { btn.innerHTML = oldHtml; }, 1800);
    });
}

// ============================================================================
// 5. THREE.JS: ПРОЦЕДУРНЫЕ 3D-ДЕТАЛИ + РЕАЛИСТИЧНЫЙ ХОТЭНД С КУЛЕРОМ И ШЛЕЙФОМ
// ============================================================================
function createFdmLayerBumpTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');
    for (let y = 0; y < 256; y += 4) {
        ctx.fillStyle = '#f1f5f9';
        ctx.fillRect(0, y, 64, 2);
        ctx.fillStyle = '#cbd5e1';
        ctx.fillRect(0, y + 2, 64, 2);
    }
    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(2, 6);
    return texture;
}

// Реалистичная текстура верхнего слоя FDM-печати (45° штриховка растра)
function createFdmTopInfillTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');

    ctx.fillStyle = '#22161e';
    ctx.fillRect(0, 0, 128, 128);

    ctx.lineWidth = 2.2;
    for (let d = -128; d < 256; d += 6) {
        ctx.strokeStyle = (d % 12 === 0) ? '#451a27' : '#2d121c';
        ctx.beginPath();
        ctx.moveTo(d, 0);
        ctx.lineTo(d + 128, 128);
        ctx.stroke();
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(3, 3);
    return texture;
}

// Калибровка цвета пластика: благородный сатиновый рубин/кармин вместо кислотного неона
function calibratePartColor(hexColor) {
    const col = new THREE.Color(hexColor || '#be123c');
    const hsl = {};
    col.getHSL(hsl);
    // Для оттенков красного/рубинового ограничиваем перенасыщение и гасим блёклость
    if (hsl.h < 0.08 || hsl.h > 0.90) {
        hsl.s = Math.min(hsl.s, 0.72);
        hsl.l = Math.max(0.28, Math.min(hsl.l, 0.38));
        col.setHSL(hsl.h, hsl.s, hsl.l);
    }
    return col;
}

function createProceduralPartGeometry(sku) {
    const code = (sku || '').toUpperCase();
    let shape;
    let maxHeight = 1.15;

    if (code.includes('DRN-ARM')) {
        maxHeight = 1.05;
        shape = new THREE.Shape();
        shape.moveTo(-1.35, -0.22);
        shape.lineTo(1.20, -0.30);
        shape.absarc(1.20, 0, 0.36, -Math.PI / 2, Math.PI / 2, false);
        shape.lineTo(-1.35, 0.22);
        shape.absarc(-1.35, 0, 0.22, Math.PI / 2, -Math.PI / 2, false);

        const motorHole = new THREE.Path();
        motorHole.absarc(1.20, 0, 0.15, 0, Math.PI * 2, true);
        shape.holes.push(motorHole);

        [-0.85, -0.32, 0.22, 0.72].forEach(xPos => {
            const slot = new THREE.Path();
            slot.absellipse(xPos, 0, 0.15, 0.09, 0, Math.PI * 2, true);
            shape.holes.push(slot);
        });
    } else if (code.includes('GEAR')) {
        maxHeight = 1.15;
        const teeth = 16;
        const outerR = 1.02;
        const innerR = 0.86;
        shape = new THREE.Shape();

        for (let i = 0; i < teeth * 2; i++) {
            const angle = (i / (teeth * 2)) * Math.PI * 2;
            const r = (i % 2 === 0) ? outerR : innerR;
            const x = Math.cos(angle) * r;
            const y = Math.sin(angle) * r;
            if (i === 0) shape.moveTo(x, y);
            else shape.lineTo(x, y);
        }
        shape.closePath();

        const centerHole = new THREE.Path();
        centerHole.absarc(0, 0, 0.26, 0, Math.PI * 2, true);
        shape.holes.push(centerHole);

        for (let i = 0; i < 4; i++) {
            const a = (i / 4) * Math.PI * 2;
            const h = new THREE.Path();
            h.absarc(Math.cos(a) * 0.54, Math.sin(a) * 0.54, 0.12, 0, Math.PI * 2, true);
            shape.holes.push(h);
        }
    } else if (code.includes('CASE-RPI')) {
        maxHeight = 1.25;
        const w = 1.85, h = 1.30, r = 0.15;
        shape = new THREE.Shape();
        shape.moveTo(-w / 2 + r, -h / 2);
        shape.lineTo(w / 2 - r, -h / 2);
        shape.quadraticCurveTo(w / 2, -h / 2, w / 2, -h / 2 + r);
        shape.lineTo(w / 2, h / 2 - r);
        shape.quadraticCurveTo(w / 2, h / 2, w / 2 - r, h / 2);
        shape.lineTo(-w / 2 + r, h / 2);
        shape.quadraticCurveTo(-w / 2, h / 2, -w / 2, h / 2 - r);
        shape.lineTo(-w / 2, -h / 2 + r);
        shape.quadraticCurveTo(-w / 2, -h / 2, -w / 2 + r, -h / 2);

        const iw = 1.54, ih = 1.00;
        const inner = new THREE.Path();
        inner.moveTo(-iw / 2, -ih / 2);
        inner.lineTo(iw / 2, -ih / 2);
        inner.lineTo(iw / 2, ih / 2);
        inner.lineTo(-iw / 2, ih / 2);
        inner.closePath();
        shape.holes.push(inner);
    } else if (code.includes('DUCT')) {
        maxHeight = 1.20;
        shape = new THREE.Shape();
        shape.absarc(0, 0, 0.90, -Math.PI * 0.25, Math.PI * 1.25, false);
        shape.absarc(0, 0, 0.54, Math.PI * 1.25, -Math.PI * 0.25, true);
        shape.closePath();
    } else {
        maxHeight = 1.20;
        shape = new THREE.Shape();
        shape.moveTo(-0.82, -0.62);
        shape.lineTo(0.82, -0.62);
        shape.lineTo(0.82, 0.62);
        shape.lineTo(0.48, 0.62);
        shape.lineTo(0.48, -0.24);
        shape.lineTo(-0.48, -0.24);
        shape.lineTo(-0.48, 0.62);
        shape.lineTo(-0.82, 0.62);
        shape.closePath();
    }

    const geo = new THREE.ExtrudeGeometry(shape, {
        depth: maxHeight,
        bevelEnabled: false,
        steps: 20,
        curveSegments: 32
    });
    geo.rotateX(-Math.PI / 2);

    geo.computeBoundingBox();
    const minY = geo.boundingBox.min.y;
    const centerX = (geo.boundingBox.max.x + geo.boundingBox.min.x) / 2;
    const centerZ = (geo.boundingBox.max.z + geo.boundingBox.min.z) / 2;
    geo.translate(-centerX, -minY, -centerZ);
    geo.computeBoundingBox();

    // 2D плоская крышка слоя среза (100% сплошное заполнение, исключает прозрачность внутри)
    const capGeo = new THREE.ShapeGeometry(shape, 32);
    capGeo.rotateX(-Math.PI / 2);
    capGeo.translate(-centerX, 0, -centerZ);

    const rawPts = shape.getSpacedPoints(240);
    const contourPoints = rawPts.map(pt => ({
        x: pt.x - centerX,
        z: -pt.y - centerZ
    }));

    const holeContours = [];
    if (shape.holes && shape.holes.length > 0) {
        shape.holes.forEach(hole => {
            const hPts = hole.getPoints(36);
            holeContours.push(hPts.map(pt => ({
                x: pt.x - centerX,
                z: -pt.y - centerZ
            })));
        });
    }

    return {
        geo,
        capGeo,
        maxHeight: geo.boundingBox.max.y,
        contourPoints,
        holeContours
    };
}

// Полный детализированный 3D-хотэнд с кулером, проводами и трубкой подачи
function createSleekHotend() {
    const group = new THREE.Group();

    const brassMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.92, roughness: 0.16 });
    const copperMat = new THREE.MeshStandardMaterial({ color: 0xd97706, metalness: 0.88, roughness: 0.22 });
    const titaniumMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.9, roughness: 0.2 });
    const alumMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.82, roughness: 0.24 });
    const darkAnodizedMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.5, roughness: 0.4 });
    const siliconeSockMat = new THREE.MeshStandardMaterial({ color: 0x881337, metalness: 0.1, roughness: 0.65 });
    const redWireMat = new THREE.MeshStandardMaterial({ color: 0xdc2626, roughness: 0.5 });

    // 1. Латунное сопло + шестигранная гайка
    const tipGeo = new THREE.ConeGeometry(0.036, 0.065, 16);
    tipGeo.rotateX(Math.PI);
    const nozzleTip = new THREE.Mesh(tipGeo, brassMat);
    nozzleTip.position.y = 0.0325;
    group.add(nozzleTip);

    const hexNut = new THREE.Mesh(new THREE.CylinderGeometry(0.048, 0.048, 0.045, 6), brassMat);
    hexNut.position.y = 0.085;
    group.add(hexNut);

    // 2. Нагревательный блок + термоносок + медный картридж
    const blockGroup = new THREE.Group();
    blockGroup.position.set(0.025, 0.17, 0);
    blockGroup.add(new THREE.Mesh(new THREE.BoxGeometry(0.19, 0.11, 0.15), alumMat));

    const sock = new THREE.Mesh(new THREE.BoxGeometry(0.196, 0.085, 0.156), siliconeSockMat);
    sock.position.y = -0.01;
    blockGroup.add(sock);

    const cartridgeGeo = new THREE.CylinderGeometry(0.028, 0.028, 0.17, 16);
    cartridgeGeo.rotateX(Math.PI / 2);
    const cartridge = new THREE.Mesh(cartridgeGeo, copperMat);
    cartridge.position.set(0.045, 0.01, 0);
    blockGroup.add(cartridge);
    group.add(blockGroup);

    // Провода нагревателя в красной оплётке
    [-0.018, 0.018].forEach(zOffset => {
        const wireCurve = new THREE.CatmullRomCurve3([
            new THREE.Vector3(0.095, 0.18, 0.075 + zOffset),
            new THREE.Vector3(0.16, 0.26, 0.06 + zOffset),
            new THREE.Vector3(0.15, 0.48, 0.03 + zOffset),
            new THREE.Vector3(0.09, 0.68, 0.01 + zOffset)
        ]);
        const wireGeo = new THREE.TubeGeometry(wireCurve, 16, 0.011, 8, false);
        group.add(new THREE.Mesh(wireGeo, redWireMat));
    });

    // 3. Титановый термобарьер и радиатор с 7 рёбрами
    const throat = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.028, 0.08, 16), titaniumMat);
    throat.position.y = 0.265;
    group.add(throat);

    const sinkCore = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.30, 16), alumMat);
    sinkCore.position.y = 0.45;
    group.add(sinkCore);

    for (let i = 0; i < 7; i++) {
        const radius = (i < 2) ? 0.115 : 0.135;
        const fin = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, 0.016, 24), alumMat);
        fin.position.y = 0.315 + i * 0.042;
        group.add(fin);
    }

    // 4. Вентилятор радиатора с вращающейся крыльчаткой
    const fanMount = new THREE.Group();
    fanMount.position.set(-0.145, 0.45, 0);
    fanMount.add(new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.26, 0.26), darkAnodizedMat));

    const fanRotor = new THREE.Group();
    fanRotor.position.x = -0.026;
    const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.02, 16), darkAnodizedMat);
    hub.rotation.z = Math.PI / 2;
    fanRotor.add(hub);

    for (let b = 0; b < 7; b++) {
        const blade = new THREE.Mesh(new THREE.BoxGeometry(0.008, 0.09, 0.028), alumMat);
        const angle = (b / 7) * Math.PI * 2;
        blade.position.set(0, Math.cos(angle) * 0.065, Math.sin(angle) * 0.065);
        blade.rotation.x = angle + 0.45;
        fanRotor.add(blade);
    }
    fanMount.add(fanRotor);
    group.add(fanMount);

    // 5. Двухсторонние сопла обдува детали
    [-1, 1].forEach(side => {
        const ductGroup = new THREE.Group();
        const channel = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.24, 0.07), darkAnodizedMat);
        channel.position.set(0, 0.22, side * 0.165);
        ductGroup.add(channel);

        const nozzleBlower = new THREE.Mesh(new THREE.ConeGeometry(0.038, 0.11, 4), darkAnodizedMat);
        nozzleBlower.position.set(0, 0.08, side * 0.115);
        nozzleBlower.rotation.x = side * 0.85;
        nozzleBlower.rotation.y = Math.PI / 4;
        ductGroup.add(nozzleBlower);
        group.add(ductGroup);
    });

    // 6. Цанговый фитинг + PTFE-трубка + цветной пруток филамента
    const colletBody = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.04, 16), brassMat);
    colletBody.position.y = 0.62;
    group.add(colletBody);

    const ptfeMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, transparent: true, opacity: 0.38, roughness: 0.2 });
    const ptfeTube = new THREE.Mesh(new THREE.CylinderGeometry(0.036, 0.036, 0.42, 16), ptfeMat);
    ptfeTube.position.y = 0.86;
    group.add(ptfeTube);

    const filamentRodMat = new THREE.MeshStandardMaterial({ color: 0xbe123c, roughness: 0.3 });
    const filamentRod = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.42, 12), filamentRodMat);
    filamentRod.position.y = 0.86;
    group.add(filamentRod);

    // 7. Светящаяся капля расплава на кончике сопла
    const meltMat = new THREE.MeshBasicMaterial({ color: 0xf43f5e });
    const meltDot = new THREE.Mesh(new THREE.SphereGeometry(0.024, 12, 12), meltMat);
    meltDot.position.y = 0.005;
    group.add(meltDot);

    const tipLight = new THREE.PointLight(0xfb7185, 1.1, 1.4);
    tipLight.position.y = 0.035;
    group.add(tipLight);

    group.scale.set(0.88, 0.88, 0.88);
    return { group, meltMat, filamentRodMat, tipLight, fanRotor };
}

class PrinterSlice3DViewer {
    constructor(container) {
        this.container = container;
        const width = Math.max(container.clientWidth, 400);
        const height = Math.max(container.clientHeight, 240);

        this.scene = new THREE.Scene();
        this.camera = new THREE.PerspectiveCamera(38, width / height, 0.1, 1000);
        this.camera.position.set(4.2, 3.3, 4.6);
        this.camera.lookAt(0, 0.5, 0);

        this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
        this.renderer.setSize(width, height);
        this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        this.renderer.localClippingEnabled = true;

        container.querySelectorAll('canvas').forEach(c => c.remove());
        container.appendChild(this.renderer.domElement);

        // Сбалансированное студийное освещение: глубина теней без выбивания цветов
        this.scene.add(new THREE.AmbientLight(0xffffff, 0.55));

        const keyLight = new THREE.DirectionalLight(0xfff7ed, 0.95);
        keyLight.position.set(5, 9, 6);
        this.scene.add(keyLight);

        const fillLight = new THREE.DirectionalLight(0xe2e8f0, 0.45);
        fillLight.position.set(-5, 5, -4);
        this.scene.add(fillLight);

        const rimLight = new THREE.DirectionalLight(0xffffff, 0.35);
        rimLight.position.set(0, 4, -6);
        this.scene.add(rimLight);

        this.bedGroup = new THREE.Group();
        this.scene.add(this.bedGroup);
        this._buildPeiPlate();

        this.targetCutHeight = 0.65;
        this.currentCutHeight = 0.65;
        this.layerBandThickness = 0.038;

        this.printedClipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), this.currentCutHeight);
        this.ghostClipPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -this.currentCutHeight);

        this.layerBumpTex = createFdmLayerBumpTexture();
        this.topInfillTex = createFdmTopInfillTexture();

        this.partGroup = new THREE.Group();
        this.bedGroup.add(this.partGroup);

        this.hotend = createSleekHotend();
        this.bedGroup.add(this.hotend.group);

        // Светящийся шлейф расплавленного пластика за соплом
        this.trailLength = 32;
        const trailPositions = new Float32Array(this.trailLength * 3);
        this.trailGeo = new THREE.BufferGeometry();
        this.trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPositions, 3));
        this.trailMat = new THREE.LineBasicMaterial({ color: 0xff385c, transparent: true, opacity: 0.95 });
        this.trailLine = new THREE.Line(this.trailGeo, this.trailMat);
        this.bedGroup.add(this.trailLine);

        this.currentSku = null;
        this.maxHeight = 1.2;
        this.contourPoints = [];
        this.contourCursor = 0;
        this.isPrinting = false;

        // Плавное вращение и интерактивное управление с авто-возобновлением
        this.isDragging = false;
        this.prevX = 0;
        this.rotY = 0.55;
        this.lastInteractTime = 0;
        this.autoRotateSpeed = 0.0016;

        const onStart = (clientX) => {
            this.isDragging = true;
            this.prevX = clientX;
            this.lastInteractTime = performance.now();
        };
        const onMove = (clientX) => {
            if (!this.isDragging) return;
            this.rotY += (clientX - this.prevX) * 0.008;
            this.prevX = clientX;
            this.lastInteractTime = performance.now();
        };
        const onEnd = () => {
            this.isDragging = false;
            this.lastInteractTime = performance.now();
        };

        container.addEventListener('mousedown', (e) => onStart(e.clientX));
        window.addEventListener('mouseup', onEnd);
        window.addEventListener('mousemove', (e) => onMove(e.clientX));

        container.addEventListener('touchstart', (e) => {
            if (e.touches && e.touches.length === 1) onStart(e.touches[0].clientX);
        }, { passive: true });
        window.addEventListener('touchend', onEnd, { passive: true });
        window.addEventListener('touchmove', (e) => {
            if (e.touches && e.touches.length === 1) onMove(e.touches[0].clientX);
        }, { passive: true });

        this.applyThemeColors(getSavedTheme());
        window.addEventListener('resize', () => this.resize());

        this.clock = 0;
        this.animate = this.animate.bind(this);
        requestAnimationFrame(this.animate);
    }

    resize() {
        if (!this.container) return;
        const w = this.container.clientWidth;
        const h = this.container.clientHeight;
        if (w > 10 && h > 10) {
            this.camera.aspect = w / h;
            this.camera.updateProjectionMatrix();
            this.renderer.setSize(w, h);
        }
    }

    _buildPeiPlate() {
        // Текстурированный матовый пружинный стол PEI (без белого бликового пятна)
        const plateGeo = new THREE.BoxGeometry(3.8, 0.08, 3.8);
        this.plateMat = new THREE.MeshStandardMaterial({
            color: 0x14121a,
            metalness: 0.12,
            roughness: 0.85
        });
        const plate = new THREE.Mesh(plateGeo, this.plateMat);
        plate.position.y = -0.04;
        this.bedGroup.add(plate);

        // Карминовая координатная сетка стола
        const grid = new THREE.GridHelper(3.6, 18, 0xbe123c, 0x2e283b);
        grid.position.y = 0.004;
        this.bedGroup.add(grid);

        // Калибровочная линия очистки сопла (Purge Line)
        const purgeGeo = new THREE.BoxGeometry(2.4, 0.012, 0.035);
        const purgeMat = new THREE.MeshBasicMaterial({ color: 0xbe123c });
        const purgeLine = new THREE.Mesh(purgeGeo, purgeMat);
        purgeLine.position.set(0, 0.008, 1.72);
        this.bedGroup.add(purgeLine);
    }

    applyThemeColors(theme) {
        if (!this.plateMat) return;
        this.plateMat.color.setHex(theme === 'light' ? 0x24202e : 0x14121a);
        if (this.printedEdges && this.printedEdges.material) {
            this.printedEdges.material.color.setHex(theme === 'light' ? 0x3d0714 : 0x6e0d22);
        }
    }

    updatePartAndProgress(data) {
        this.resize();
        const pct = Math.max(0, Math.min(100, data.progress || 0));
        this.isPrinting = (data.status === 'printing' && data.has_active_job && pct < 100);
        const sku = data.has_active_job ? data.sku : 'GEAR-PLANET';

        // Откалиброванный благородный сатиновый рубин/кармин
        const displayColor = calibratePartColor(data.spool_hex || '#be123c');

        if (this.hotend && this.hotend.filamentRodMat) {
            this.hotend.filamentRodMat.color.copy(displayColor);
        }

        if (this.currentSku !== sku) {
            while (this.partGroup.children.length > 0) {
                this.partGroup.remove(this.partGroup.children[0]);
            }
            this.currentSku = sku;

            const built = createProceduralPartGeometry(sku);
            this.maxHeight = built.maxHeight;
            this.contourPoints = built.contourPoints;

            // 1. Основное объёмное тело детали (сатиновый благородный пластик с микроструктурой слоёв)
            const frontMat = new THREE.MeshStandardMaterial({
                color: displayColor,
                metalness: 0.08,
                roughness: 0.48,
                bumpMap: this.layerBumpTex,
                bumpScale: 0.008,
                side: THREE.FrontSide,
                clippingPlanes: [this.printedClipPlane]
            });
            this.frontMesh = new THREE.Mesh(built.geo, frontMat);
            this.partGroup.add(this.frontMesh);

            // 2. Сплошная верхняя крышка слоя среза (100% заполнение, исключает прозрачность)
            const topCapMat = new THREE.MeshStandardMaterial({
                color: displayColor.clone().offsetHSL(0, -0.03, 0.04),
                metalness: 0.05,
                roughness: 0.42,
                bumpMap: this.topInfillTex,
                bumpScale: 0.006,
                side: THREE.DoubleSide
            });
            this.topCapMesh = new THREE.Mesh(built.capGeo, topCapMat);
            this.partGroup.add(this.topCapMesh);

            // 3. Чёткие контуры граней (зубья, фаски, отверстия видны максимально контрастно)
            const edgesGeo = new THREE.EdgesGeometry(built.geo, 16);
            const edgeHex = getSavedTheme() === 'light' ? 0x3d0714 : 0x6e0d22;
            const printedEdgesMat = new THREE.LineBasicMaterial({
                color: edgeHex,
                linewidth: 1.5,
                clippingPlanes: [this.printedClipPlane]
            });
            this.printedEdges = new THREE.LineSegments(edgesGeo, printedEdgesMat);
            this.partGroup.add(this.printedEdges);

            // 4. Активный периметр спекания внешнего контура соплом
            const perimeterPoints = this.contourPoints.map(p => new THREE.Vector3(p.x, 0, p.z));
            const perimeterGeo = new THREE.BufferGeometry().setFromPoints(perimeterPoints);
            const activePerimeterMat = new THREE.LineBasicMaterial({
                color: 0xff385c,
                linewidth: 2.2
            });
            this.activePerimeterLine = new THREE.LineLoop(perimeterGeo, activePerimeterMat);
            this.partGroup.add(this.activePerimeterLine);

            // 5. Активные периметры внутренних отверстий
            this.holePerimeterGroup = new THREE.Group();
            if (built.holeContours && built.holeContours.length > 0) {
                built.holeContours.forEach(hPts => {
                    const hGeo = new THREE.BufferGeometry().setFromPoints(hPts.map(p => new THREE.Vector3(p.x, 0, p.z)));
                    const hLine = new THREE.LineLoop(hGeo, new THREE.LineBasicMaterial({ color: 0xff385c, linewidth: 1.8 }));
                    this.holePerimeterGroup.add(hLine);
                });
            }
            this.partGroup.add(this.holePerimeterGroup);

            // 6. Полупрозрачный контур будущей модели над слоем печати
            const ghostMat = new THREE.LineBasicMaterial({
                color: 0x64748b,
                transparent: true,
                opacity: 0.16,
                clippingPlanes: [this.ghostClipPlane]
            });
            this.ghostEdges = new THREE.LineSegments(edgesGeo, ghostMat);
            this.partGroup.add(this.ghostEdges);
        } else {
            if (this.frontMesh) this.frontMesh.material.color.copy(displayColor);
            if (this.topCapMesh) this.topCapMesh.material.color.copy(displayColor.clone().offsetHSL(0, -0.03, 0.04));
        }

        this.targetCutHeight = (pct / 100.0) * this.maxHeight;
        if (this.ghostEdges) this.ghostEdges.visible = (pct < 100);
        if (this.hotend) this.hotend.group.visible = (pct > 0 && pct < 100);
        if (this.trailLine) this.trailLine.visible = (pct > 0 && pct < 100 && this.contourPoints.length > 0);
    }

    animate() {
        requestAnimationFrame(this.animate);
        this.clock += 0.03;

        // Плавный поворот витрины при бездействии пользователя (> 3.5 сек)
        const timeSinceInteract = performance.now() - this.lastInteractTime;
        if (!this.isDragging && timeSinceInteract > 3500) {
            this.rotY += this.autoRotateSpeed;
        }
        this.bedGroup.rotation.y += (this.rotY - this.bedGroup.rotation.y) * 0.08;

        // Вращение крыльчатки кулера охлаждения
        if (this.hotend && this.hotend.fanRotor) {
            this.hotend.fanRotor.rotation.x += 0.35;
        }

        // Дыхание накала сопла (эффект нагревательного блока)
        if (this.hotend && this.hotend.tipLight) {
            const heatGlow = 0.8 + 0.2 * Math.sin(this.clock * 4.5);
            this.hotend.tipLight.intensity = heatGlow * 1.0;
        }

        this.currentCutHeight += (this.targetCutHeight - this.currentCutHeight) * 0.1;

        this.printedClipPlane.constant = this.currentCutHeight;
        this.ghostClipPlane.constant = -this.currentCutHeight;

        const isActivelyPrinting = this.currentCutHeight > 0.02 && this.currentCutHeight < this.maxHeight - 0.01;

        if (this.topCapMesh) {
            this.topCapMesh.position.y = this.currentCutHeight;
            this.topCapMesh.visible = (this.currentCutHeight > 0.015);
        }

        if (this.activePerimeterLine) {
            this.activePerimeterLine.position.y = this.currentCutHeight + 0.002;
            this.activePerimeterLine.visible = isActivelyPrinting;
        }

        if (this.holePerimeterGroup) {
            this.holePerimeterGroup.position.y = this.currentCutHeight + 0.002;
            this.holePerimeterGroup.visible = isActivelyPrinting;
        }

        const layerY = Math.max(0.01, this.currentCutHeight);

        if (this.contourPoints.length > 1) {
            this.contourCursor = (this.contourCursor + 0.85) % this.contourPoints.length;
            const totalPts = this.contourPoints.length;
            const idx0 = Math.floor(this.contourCursor);
            const idx1 = (idx0 + 1) % totalPts;
            const frac = this.contourCursor - idx0;

            const p0 = this.contourPoints[idx0];
            const p1 = this.contourPoints[idx1];
            const curX = p0.x + (p1.x - p0.x) * frac;
            const curZ = p0.z + (p1.z - p0.z) * frac;

            this.hotend.group.position.set(curX, layerY, curZ);

            const posArr = this.trailGeo.attributes.position.array;
            for (let i = 0; i < this.trailLength; i++) {
                const backIdx = (idx0 - i + totalPts * 2) % totalPts;
                const pt = this.contourPoints[backIdx];
                posArr[i * 3] = pt.x;
                posArr[i * 3 + 1] = layerY + 0.006;
                posArr[i * 3 + 2] = pt.z;
            }
            this.trailGeo.attributes.position.needsUpdate = true;
        }

        this.renderer.render(this.scene, this.camera);
    }
}

async function initOverviewPrintBed3D(container) {
    const printerId = container.dataset.printerId;
    overviewViewer = new PrinterSlice3DViewer(container);

    if (printerId) {
        try {
            const res = await fetch(`/api/printer/${printerId}/telemetry`);
            if (res.ok) {
                const data = await res.json();
                overviewViewer.updatePartAndProgress(data);

                const skuEl = document.getElementById('overview-part-sku');
                if (skuEl) skuEl.textContent = data.sku;

                const remEl = document.getElementById('overview-remaining');
                if (remEl) remEl.textContent = data.remaining_ru;

                const layerEl = document.getElementById('overview-layer-badge');
                if (layerEl && data.has_active_job) {
                    layerEl.innerHTML = `<i class="bi bi-layers-fill me-1"></i> Слой: ${data.current_layer} из ${data.total_layers} (${data.progress}%)`;
                }
                return;
            }
        } catch (err) {
            console.error('Ошибка загрузки 3D-обзора:', err);
        }
    }

    overviewViewer.updatePartAndProgress({
        status: 'printing',
        has_active_job: true,
        sku: 'GEAR-PLANET',
        spool_hex: '#9f1239',
        progress: 45
    });
}

async function openPrinterTelemetryModal(printerId) {
    await ensureThreeJsLoaded();
    const modalEl = document.getElementById('printerTelemetryModal');
    if (!modalEl) return;

    currentTelemetryPrinterId = printerId;
    telemetryChangedFlag = false;

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    await refreshPrinterTelemetryData(printerId);

    setTimeout(() => { if (telemetryViewer) telemetryViewer.resize(); }, 80);
    setTimeout(() => { if (telemetryViewer) telemetryViewer.resize(); }, 250);
}

async function refreshPrinterTelemetryData(printerId) {
    try {
        const res = await fetch(`/api/printer/${printerId}/telemetry`);
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById('tel-printer-title').textContent = `${data.printer_name} — ${data.printer_model}`;
        const stBadge = document.getElementById('tel-printer-status');
        stBadge.textContent = data.status_ru;
        stBadge.className = `status-pill pill-${data.status}`;

        document.getElementById('tel-part-name').textContent = data.product_name;
        document.getElementById('tel-part-sku').textContent = data.sku;
        document.getElementById('tel-order-info').textContent = data.has_active_job
            ? `${data.order_num} (${data.client_name}) • Партия: ${data.quantity} шт.`
            : 'Ожидание постановки задания из очереди';

        document.getElementById('tel-spool-name').textContent = `${data.spool_material} (${data.spool_color})`;
        document.getElementById('tel-spool-weight').textContent = `${data.spool_weight} из ${data.spool_init_weight} г`;
        document.getElementById('tel-spool-dot').style.backgroundColor = data.spool_hex;

        document.getElementById('tel-nozzle-temp').textContent = `${data.nozzle_temp} °C`;
        document.getElementById('tel-nozzle-target').textContent = `Цель: ${data.nozzle_target} °C`;
        document.getElementById('tel-bed-temp').textContent = `${data.bed_temp} °C`;
        document.getElementById('tel-bed-target').textContent = `Цель: ${data.bed_target} °C`;

        document.getElementById('tel-speed').textContent = data.print_speed;
        document.getElementById('tel-fan').textContent = data.fan_speed;
        document.getElementById('tel-remaining').textContent = data.remaining_ru;

        document.getElementById('tel-progress-pct').textContent = `${data.progress}%`;
        document.getElementById('tel-progress-bar').style.width = `${data.progress}%`;

        const layerText = data.has_active_job
            ? `Слой: ${data.current_layer} из ${data.total_layers} (${data.progress}% готово)`
            : 'Станок в режиме ожидания';
        document.getElementById('tel-layer-badge').innerHTML = `<i class="bi bi-layers-fill me-1"></i> ${layerText}`;

        const failForm = document.getElementById('tel-fail-form');
        if (failForm) {
            if (data.job_id) {
                failForm.action = `/queue/${data.job_id}/fail`;
                failForm.classList.remove('d-none');
            } else {
                failForm.classList.add('d-none');
            }
        }

        const container = document.getElementById('telemetry3d-canvas-container');
        if (!container) return;
        if (!telemetryViewer) {
            telemetryViewer = new PrinterSlice3DViewer(container);
        }
        telemetryViewer.updatePartAndProgress(data);
    } catch (e) {
        console.error('Ошибка загрузки телеметрии:', e);
    }
}

async function stepPrinterInModal() {
    if (!currentTelemetryPrinterId) return;
    const btn = document.getElementById('btn-modal-step');
    if (btn) btn.disabled = true;
    try {
        await fetch('/api/simulator/tick', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ printer_id: currentTelemetryPrinterId })
        });
        telemetryChangedFlag = true;
        await refreshPrinterTelemetryData(currentTelemetryPrinterId);
    } finally {
        if (btn) btn.disabled = false;
    }
}
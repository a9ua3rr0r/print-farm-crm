let telemetryViewer = null;
let currentTelemetryPrinterId = null;
let telemetryChangedFlag = false;

// Автоподгрузка Three.js, если скрипт не был подключен в base.html
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

// Автоматическое создание модального окна 3D-телеметрии, если оно отсутствует в шаблоне
function ensureTelemetryModalExists() {
    let modalEl = document.getElementById('printerTelemetryModal');
    if (modalEl && document.getElementById('telemetry3d-canvas-container')) {
        return modalEl;
    }

    const wrapper = document.createElement('div');
    wrapper.innerHTML = `
    <div class="modal fade" id="printerTelemetryModal" tabindex="-1">
        <div class="modal-dialog modal-xl modal-dialog-centered">
            <div class="modal-content">
                <div class="modal-header border-secondary border-opacity-25">
                    <div class="d-flex align-items-center gap-3">
                        <div class="p-2 rounded-3 bg-primary bg-opacity-25 text-primary">
                            <i class="bi bi-badge-3d-fill fs-4"></i>
                        </div>
                        <div>
                            <div class="small text-muted">ЦИФРОВОЙ ДВОЙНИК И ПОСЛОЙНЫЙ КОНТРОЛЬ FDM</div>
                            <h5 class="modal-title fw-bold mb-0 text-white" id="tel-printer-title">Загрузка станка...</h5>
                        </div>
                    </div>
                    <div class="d-flex align-items-center gap-3">
                        <span id="tel-printer-status" class="status-pill pill-idle">Свободен</span>
                        <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
                    </div>
                </div>
                <div class="modal-body p-4">
                    <div class="row g-4">
                        <div class="col-lg-7">
                            <div id="telemetry3d-canvas-container" style="width: 100%; height: 410px; position: relative; border-radius: 0.85rem; overflow: hidden; background: radial-gradient(circle at center, #17253f 0%, #070a12 100%); border: 1px solid rgba(59, 130, 246, 0.35); cursor: grab;">
                                <div class="canvas-overlay-badge">
                                    <i class="bi bi-camera-video-fill text-primary me-1"></i> Камера 3D-среза (вращайте мышью)
                                </div>
                                <div class="canvas-overlay-layer" id="tel-layer-badge">
                                    <i class="bi bi-layers-fill me-1"></i> Слой: 0 из 0
                                </div>
                            </div>
                        </div>
                        <div class="col-lg-5 d-flex flex-column justify-content-between">
                            <div>
                                <div class="p-3 rounded-3 bg-dark border border-secondary border-opacity-25 mb-3">
                                    <div class="d-flex justify-content-between align-items-center mb-1">
                                        <span class="badge bg-primary bg-opacity-25 text-primary" id="tel-part-sku">SKU</span>
                                        <span class="small text-muted">Осталось: <strong class="text-white" id="tel-remaining">—</strong></span>
                                    </div>
                                    <h6 class="fw-bold text-white mb-1" id="tel-part-name">—</h6>
                                    <div class="small text-muted mb-3" id="tel-order-info">—</div>

                                    <div class="d-flex justify-content-between small mb-1">
                                        <span class="text-muted">Готовность по слоям:</span>
                                        <span class="fw-bold text-primary" id="tel-progress-pct">0%</span>
                                    </div>
                                    <div class="progress" style="height: 10px;">
                                        <div id="tel-progress-bar" class="progress-bar progress-bar-striped progress-bar-animated bg-primary" style="width: 0%"></div>
                                    </div>
                                </div>

                                <div class="row g-2 mb-3">
                                    <div class="col-6">
                                        <div class="telemetry-sensor-box">
                                            <div class="small text-muted"><i class="bi bi-thermometer-high text-danger me-1"></i>Экструдер (Сопло)</div>
                                            <div class="fs-5 fw-bold text-white" id="tel-nozzle-temp">25 °C</div>
                                            <div class="text-muted" style="font-size: 0.72rem;" id="tel-nozzle-target">Цель: 0 °C</div>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="telemetry-sensor-box">
                                            <div class="small text-muted"><i class="bi bi-grid-3x3 text-warning me-1"></i>Стол нагрева (PEI)</div>
                                            <div class="fs-5 fw-bold text-white" id="tel-bed-temp">24 °C</div>
                                            <div class="text-muted" style="font-size: 0.72rem;" id="tel-bed-target">Цель: 0 °C</div>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="telemetry-sensor-box">
                                            <div class="small text-muted"><i class="bi bi-speedometer2 text-info me-1"></i>Скорость подачи</div>
                                            <div class="fw-bold text-white" id="tel-speed">0 мм/с</div>
                                        </div>
                                    </div>
                                    <div class="col-6">
                                        <div class="telemetry-sensor-box">
                                            <div class="small text-muted"><i class="bi bi-fan text-success me-1"></i>Обдув модели</div>
                                            <div class="fw-bold text-white" id="tel-fan">0%</div>
                                        </div>
                                    </div>
                                </div>

                                <div class="telemetry-sensor-box mb-3 d-flex justify-content-between align-items-center">
                                    <div class="d-flex align-items-center gap-2">
                                        <span id="tel-spool-dot" class="spool-color-dot"></span>
                                        <div>
                                            <div class="small text-muted" style="font-size: 0.72rem;">АКТИВНАЯ КАТУШКА ФИЛАМЕНТА</div>
                                            <div class="fw-bold text-white small" id="tel-spool-name">—</div>
                                        </div>
                                    </div>
                                    <span class="badge bg-dark border border-secondary text-info" id="tel-spool-weight">0 г</span>
                                </div>
                            </div>

                            <div class="d-flex gap-2 pt-2 border-top border-secondary border-opacity-25">
                                <button type="button" id="btn-modal-step" onclick="stepPrinterInModal()" class="btn btn-warning fw-semibold text-dark flex-grow-1">
                                    <i class="bi bi-fast-forward-fill me-1"></i> Напечатать +20% слоёв
                                </button>
                                <form id="tel-fail-form" method="POST" action="">
                                    <input type="hidden" name="reason" value="Остановка оператором через 3D-телеметрию (дефект слоя)">
                                    <button type="submit" class="btn btn-outline-danger">
                                        <i class="bi bi-exclamation-octagon me-1"></i> Брак
                                    </button>
                                </form>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>`;

    document.body.appendChild(wrapper.firstElementChild);
    modalEl = document.getElementById('printerTelemetryModal');

    modalEl.addEventListener('shown.bs.modal', () => {
        if (telemetryViewer) {
            telemetryViewer.resize();
        }
    });

    modalEl.addEventListener('hidden.bs.modal', () => {
        if (telemetryChangedFlag) {
            window.location.reload();
        }
    });

    return modalEl;
}

document.addEventListener('DOMContentLoaded', async () => {
    // 1. Кнопка ручного шага симулятора в сайдбаре
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

    // 2. Тумблер автоматической фоновой печати
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

    // 3. Гарантируем наличие Three.js и модального окна телеметрии
    await ensureThreeJsLoaded();
    const telModalEl = ensureTelemetryModalExists();
    telModalEl.addEventListener('shown.bs.modal', () => {
        if (telemetryViewer) telemetryViewer.resize();
    });

    // 4. Инициализация 3D-виджета ближайшей к завершению печати на Дашборде
    const overviewContainer = document.getElementById('farm3d-canvas-container');
    if (overviewContainer && typeof THREE !== 'undefined') {
        initOverviewPrintBed3D(overviewContainer);
    }

    // 5. Восстановление выбранного режима просмотра (Карточки / Стеллаж)
    const savedView = localStorage.getItem('printfarm_printers_view') || 'cards';
    if (document.getElementById('view-cards') && document.getElementById('view-rack')) {
        switchPrintersView(savedView);
    }
});

// ============================================================================
// ФИЛЬТРАЦИЯ ПРИНТЕРОВ ПО СТАТУСУ И ПЕРЕКЛЮЧЕНИЕ ВИДА (КАРТОЧКИ / СТЕЛЛАЖ)
// ============================================================================
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

// Управление строками позиций в модальном окне создания заказа
function addOrderItemRow() {
    const container = document.getElementById('items-container');
    if (!container) return;
    const firstRow = container.querySelector('.item-row');
    if (!firstRow) return;

    const clone = firstRow.cloneNode(true);
    clone.querySelector('select').selectedIndex = 0;
    clone.querySelector('input[type="number"]').value = 1;
    container.appendChild(clone);
    if (typeof calculateOrderEconomics === 'function') calculateOrderEconomics();
}

function removeOrderItemRow(btn) {
    const rows = document.querySelectorAll('#items-container .item-row');
    if (rows.length > 1) {
        btn.closest('.item-row').remove();
        if (typeof calculateOrderEconomics === 'function') calculateOrderEconomics();
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
// ПРОЦЕДУРНАЯ МИКРОТЕКСТУРА СЛОЁВ FDM-ПЕЧАТИ
// ============================================================================
function createFdmLayerBumpTexture() {
    const canvas = document.createElement('canvas');
    canvas.width = 64;
    canvas.height = 256;
    const ctx = canvas.getContext('2d');

    for (let y = 0; y < 256; y += 4) {
        ctx.fillStyle = '#ffffff';
        ctx.fillRect(0, y, 64, 2);
        ctx.fillStyle = '#94a3b8';
        ctx.fillRect(0, y + 2, 64, 2);
    }

    const texture = new THREE.CanvasTexture(canvas);
    texture.wrapS = THREE.RepeatWrapping;
    texture.wrapT = THREE.RepeatWrapping;
    texture.repeat.set(2, 6);
    return texture;
}

// ============================================================================
// ИНЖЕНЕРНЫЕ 3D-МОДЕЛИ ДЕТАЛЕЙ + ТОЧНЫЙ КОНТУР ДЛЯ ДВИЖЕНИЯ ХОТЭНДА
// ============================================================================
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

    const rawPts = shape.getSpacedPoints(240);
    const contourPoints = rawPts.map(pt => ({
        x: pt.x - centerX,
        z: -pt.y - centerZ
    }));

    return {
        geo,
        maxHeight: geo.boundingBox.max.y,
        contourPoints
    };
}

// ============================================================================
// ДЕТАЛИЗИРОВАННЫЙ ИНЖЕНЕРНЫЙ 3D-ХОТЭНД (E3D V6 / BAMBU LAB STYLE)
// ============================================================================
function createSleekHotend() {
    const group = new THREE.Group();

    const brassMat = new THREE.MeshStandardMaterial({ color: 0xf59e0b, metalness: 0.92, roughness: 0.16 });
    const copperMat = new THREE.MeshStandardMaterial({ color: 0xd97706, metalness: 0.88, roughness: 0.22 });
    const titaniumMat = new THREE.MeshStandardMaterial({ color: 0xe2e8f0, metalness: 0.9, roughness: 0.2 });
    const alumMat = new THREE.MeshStandardMaterial({ color: 0x94a3b8, metalness: 0.82, roughness: 0.24 });
    const darkAnodizedMat = new THREE.MeshStandardMaterial({ color: 0x1e293b, metalness: 0.5, roughness: 0.4 });
    const siliconeSockMat = new THREE.MeshStandardMaterial({ color: 0x0284c7, metalness: 0.1, roughness: 0.65 });
    const redWireMat = new THREE.MeshStandardMaterial({ color: 0xdc2626, roughness: 0.5 });

    // 1. Латунное сопло + шестигранник
    const tipGeo = new THREE.ConeGeometry(0.036, 0.065, 16);
    tipGeo.rotateX(Math.PI);
    const nozzleTip = new THREE.Mesh(tipGeo, brassMat);
    nozzleTip.position.y = 0.0325;
    group.add(nozzleTip);

    const hexNut = new THREE.Mesh(new THREE.CylinderGeometry(0.048, 0.048, 0.045, 6), brassMat);
    hexNut.position.y = 0.085;
    group.add(hexNut);

    // 2. Нагревательный блок + силиконовый носок + патрон нагревателя
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

    // Силовые провода нагревателя
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

    // 3. Титановый термобарьер
    const throat = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.028, 0.08, 16), titaniumMat);
    throat.position.y = 0.265;
    group.add(throat);

    // 4. Алюминиевый радиатор с 7 ребрами
    const sinkCore = new THREE.Mesh(new THREE.CylinderGeometry(0.055, 0.055, 0.30, 16), alumMat);
    sinkCore.position.y = 0.45;
    group.add(sinkCore);

    for (let i = 0; i < 7; i++) {
        const radius = (i < 2) ? 0.115 : 0.135;
        const fin = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, 0.016, 24), alumMat);
        fin.position.y = 0.315 + i * 0.042;
        group.add(fin);
    }

    // 5. Кулер охлаждения радиатора с вращающейся крыльчаткой
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

    // 6. Двухсторонние сопла обдува модели
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

    // 7. Фитинг и PTFE-трубка с прутком пластика
    const colletBody = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.04, 16), brassMat);
    colletBody.position.y = 0.62;
    group.add(colletBody);

    const ptfeMat = new THREE.MeshStandardMaterial({ color: 0xf8fafc, transparent: true, opacity: 0.38, roughness: 0.2 });
    const ptfeTube = new THREE.Mesh(new THREE.CylinderGeometry(0.036, 0.036, 0.42, 16), ptfeMat);
    ptfeTube.position.y = 0.86;
    group.add(ptfeTube);

    const filamentRodMat = new THREE.MeshStandardMaterial({ color: 0x3b82f6, roughness: 0.3 });
    const filamentRod = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.42, 12), filamentRodMat);
    filamentRod.position.y = 0.86;
    group.add(filamentRod);

    // 8. Капля расплава на кончике сопла
    const meltMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
    const meltDot = new THREE.Mesh(new THREE.SphereGeometry(0.024, 12, 12), meltMat);
    meltDot.position.y = 0.005;
    group.add(meltDot);

    const tipLight = new THREE.PointLight(0x38bdf8, 1.1, 1.4);
    tipLight.position.y = 0.035;
    group.add(tipLight);

    group.scale.set(0.88, 0.88, 0.88);
    return { group, meltMat, filamentRodMat, tipLight, fanRotor };
}

// ============================================================================
// КЛАСС 3D-ВИЗУАЛИЗАЦИИ: ПОСЛОЙНЫЙ СРЕЗ + ДВИЖЕНИЕ СОПЛА ПО КОНТУРУ ДЕТАЛИ
// ============================================================================
class PrinterSlice3DViewer {
    constructor(container) {
        this.container = container;
        const width = Math.max(container.clientWidth, 420);
        const height = Math.max(container.clientHeight, 300);

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

        this.scene.add(new THREE.AmbientLight(0xffffff, 0.95));

        const keyLight = new THREE.DirectionalLight(0xe0f2fe, 1.6);
        keyLight.position.set(5, 9, 6);
        this.scene.add(keyLight);

        const fillLight = new THREE.DirectionalLight(0x3b82f6, 0.85);
        fillLight.position.set(-5, 5, -4);
        this.scene.add(fillLight);

        this.bedGroup = new THREE.Group();
        this.scene.add(this.bedGroup);
        this._buildPeiPlate();

        this.targetCutHeight = 0.65;
        this.currentCutHeight = 0.65;
        this.layerBandThickness = 0.038;

        this.printedClipPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), this.currentCutHeight);
        this.layerBottomPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -(this.currentCutHeight - this.layerBandThickness));
        this.ghostClipPlane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -this.currentCutHeight);

        this.layerBumpTex = createFdmLayerBumpTexture();

        this.partGroup = new THREE.Group();
        this.bedGroup.add(this.partGroup);

        this.hotend = createSleekHotend();
        this.bedGroup.add(this.hotend.group);

        this.trailLength = 35;
        const trailPositions = new Float32Array(this.trailLength * 3);
        this.trailGeo = new THREE.BufferGeometry();
        this.trailGeo.setAttribute('position', new THREE.BufferAttribute(trailPositions, 3));
        this.trailMat = new THREE.LineBasicMaterial({ color: 0x38bdf8, transparent: true, opacity: 0.95 });
        this.trailLine = new THREE.Line(this.trailGeo, this.trailMat);
        this.bedGroup.add(this.trailLine);

        this.currentSku = null;
        this.maxHeight = 1.2;
        this.contourPoints = [];
        this.contourCursor = 0;
        this.isPrinting = false;

        this.isDragging = false;
        this.prevX = 0;
        this.rotY = 0.5;
        container.addEventListener('mousedown', (e) => { this.isDragging = true; this.prevX = e.clientX; });
        window.addEventListener('mouseup', () => { this.isDragging = false; });
        window.addEventListener('mousemove', (e) => {
            if (!this.isDragging) return;
            this.rotY += (e.clientX - this.prevX) * 0.01;
            this.prevX = e.clientX;
        });

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
        const plateGeo = new THREE.BoxGeometry(3.8, 0.1, 3.8);
        const plateMat = new THREE.MeshStandardMaterial({ color: 0x0f172a, metalness: 0.55, roughness: 0.35 });
        const plate = new THREE.Mesh(plateGeo, plateMat);
        plate.position.y = -0.05;
        this.bedGroup.add(plate);

        const grid = new THREE.GridHelper(3.6, 18, 0x3b82f6, 0x1e293b);
        grid.position.y = 0.004;
        this.bedGroup.add(grid);

        const purgeGeo = new THREE.BoxGeometry(2.4, 0.012, 0.035);
        const purgeMat = new THREE.MeshBasicMaterial({ color: 0x38bdf8 });
        const purgeLine = new THREE.Mesh(purgeGeo, purgeMat);
        purgeLine.position.set(0, 0.008, 1.72);
        this.bedGroup.add(purgeLine);
    }

    updatePartAndProgress(data) {
        this.resize();
        const pct = Math.max(0, Math.min(100, data.progress || 0));
        this.isPrinting = (data.status === 'printing' && data.has_active_job && pct < 100);
        const sku = data.has_active_job ? data.sku : 'IDLE';
        const baseColor = new THREE.Color(data.spool_hex || '#3b82f6');

        const displayColor = baseColor.clone();
        if (displayColor.r < 0.22 && displayColor.g < 0.22 && displayColor.b < 0.25) {
            displayColor.setHex(0x334155);
        }
        const capColor = displayColor.clone().lerp(new THREE.Color(0x60a5fa), 0.28);

        if (this.hotend && this.hotend.filamentRodMat) {
            this.hotend.filamentRodMat.color.copy(displayColor);
        }

        if (this.currentSku !== sku) {
            while (this.partGroup.children.length > 0) {
                this.partGroup.remove(this.partGroup.children[0]);
            }
            this.currentSku = sku;

            if (data.has_active_job) {
                const built = createProceduralPartGeometry(sku);
                this.maxHeight = built.maxHeight;
                this.contourPoints = built.contourPoints;

                const frontMat = new THREE.MeshStandardMaterial({
                    color: displayColor,
                    metalness: 0.25,
                    roughness: 0.35,
                    bumpMap: this.layerBumpTex,
                    bumpScale: 0.015,
                    side: THREE.FrontSide,
                    clippingPlanes: [this.printedClipPlane]
                });
                this.frontMesh = new THREE.Mesh(built.geo, frontMat);
                this.partGroup.add(this.frontMesh);

                const backCapMat = new THREE.MeshBasicMaterial({
                    color: capColor,
                    side: THREE.BackSide,
                    clippingPlanes: [this.printedClipPlane]
                });
                this.backCapMesh = new THREE.Mesh(built.geo, backCapMat);
                this.partGroup.add(this.backCapMesh);

                const activeLayerMat = new THREE.MeshBasicMaterial({
                    color: 0x38bdf8,
                    side: THREE.DoubleSide,
                    clippingPlanes: [this.printedClipPlane, this.layerBottomPlane]
                });
                this.activeLayerMesh = new THREE.Mesh(built.geo, activeLayerMat);
                this.partGroup.add(this.activeLayerMesh);

                const edgesGeo = new THREE.EdgesGeometry(built.geo, 22);
                const ghostMat = new THREE.LineBasicMaterial({
                    color: 0x64748b,
                    transparent: true,
                    opacity: 0.2,
                    clippingPlanes: [this.ghostClipPlane]
                });
                this.ghostEdges = new THREE.LineSegments(edgesGeo, ghostMat);
                this.partGroup.add(this.ghostEdges);
            } else {
                this.contourPoints = [];
            }
        } else if (this.frontMesh) {
            this.frontMesh.material.color.copy(displayColor);
            this.backCapMesh.material.color.copy(capColor);
        }

        this.targetCutHeight = data.has_active_job ? (pct / 100.0) * this.maxHeight : 0.0;

        if (this.activeLayerMesh) {
            this.activeLayerMesh.visible = data.has_active_job && pct > 0 && pct < 100;
        }
        if (this.ghostEdges) {
            this.ghostEdges.visible = data.has_active_job && pct < 100;
        }
        this.hotend.group.visible = data.has_active_job && pct > 0 && pct < 100;
        this.trailLine.visible = this.isPrinting && this.contourPoints.length > 0;
    }

    animate() {
        requestAnimationFrame(this.animate);
        this.clock += 0.03;

        if (!this.isDragging) {
            this.rotY += 0.003;
        }
        this.bedGroup.rotation.y += (this.rotY - this.bedGroup.rotation.y) * 0.1;

        if (this.hotend && this.hotend.fanRotor) {
            this.hotend.fanRotor.rotation.x += 0.35;
        }

        this.currentCutHeight += (this.targetCutHeight - this.currentCutHeight) * 0.1;

        this.printedClipPlane.constant = this.currentCutHeight;
        this.layerBottomPlane.constant = -(this.currentCutHeight - this.layerBandThickness);
        this.ghostClipPlane.constant = -this.currentCutHeight;

        const layerY = Math.max(0.01, this.currentCutHeight);

        if (this.isPrinting && this.contourPoints.length > 1) {
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
    const viewer = new PrinterSlice3DViewer(container);
    const printerId = container.dataset.printerId;

    if (printerId) {
        try {
            const res = await fetch(`/api/printer/${printerId}/telemetry`);
            if (res.ok) {
                const data = await res.json();
                viewer.updatePartAndProgress(data);

                const skuEl = document.getElementById('overview-part-sku');
                if (skuEl && data.sku) skuEl.textContent = data.sku;

                const remEl = document.getElementById('overview-remaining');
                if (remEl && data.remaining_ru) remEl.textContent = data.remaining_ru;

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

    // Если все станки свободны — показываем демонстрационную шестерню, чтобы экран не пустовал
    viewer.updatePartAndProgress({
        status: 'printing',
        has_active_job: true,
        sku: 'GEAR-PLANET',
        spool_hex: '#2563eb',
        progress: 65
    });
}

// ============================================================================
// ОТКРЫТИЕ МОДАЛЬНОГО ОКНА 3D-ТЕЛЕМЕТРИИ ЛЮБОГО ПРИНТЕРА
// ============================================================================
async function openPrinterTelemetryModal(printerId) {
    await ensureThreeJsLoaded();
    const modalEl = ensureTelemetryModalExists();

    currentTelemetryPrinterId = printerId;
    telemetryChangedFlag = false;

    const modal = bootstrap.Modal.getOrCreateInstance(modalEl);
    modal.show();

    await refreshPrinterTelemetryData(printerId);

    // Пересчитываем размер 3D-холста после завершения анимации открытия модального окна
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
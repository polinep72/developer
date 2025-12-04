let currentUser = null;
let latestDashboardPayload = null;
let latestDashboardFilters = null;

document.addEventListener("DOMContentLoaded", async () => {
    const config = getPortalConfig();
    await initAuth();
    initTabs();
    initHistorySubtabs();
    initHeatmap({
        graphId: "heatmap-graph",
        buttonId: "refresh-heatmap",
        dateInputId: "booking-date",
        errorId: "heatmap-error",
        updatedAtId: "updated-at",
        initialFigure: config.initialFigure,
        initialError: config.errorMessage,
        buttonText: "Показать занятость",
        summaryConfig: {activeId: "active-bookings", freeId: "free-slots"},
        initialSummary: config.initialSummary || null,
    });
    initHeatmap({
        graphId: "history-heatmap-graph",
        buttonId: "history-heatmap-btn",
        dateInputId: "history-date",
        errorId: "history-heatmap-error",
        updatedAtId: null,
        initialFigure: config.historyFigure,
        initialError: config.historyError,
        buttonText: "Показать историю",
        maxDate: config.today,
        hideLegend: true,
    });
    initBookingForm();
    initManageBookings();
    initDashboard();
    initCalendar();
    initEquipmentModule();
    initUsersManagement();
    initUserProfilePanel();
});

function getPortalConfig() {
    const raw = document.body.dataset.config;
    try {
        return JSON.parse(raw || "{}");
    } catch {
        return {};
    }
}

function initTabs() {
    const buttons = document.querySelectorAll(".tab-button");
    const contents = document.querySelectorAll(".tab-content");
    const workplacesTabId = "tab-workplaces";

    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            // Не переключаемся на скрытые вкладки
            if (button.classList.contains("hidden")) {
                return;
            }
            
            const target = button.dataset.tab;

            buttons.forEach((btn) => btn.classList.toggle("active", btn === button));
            contents.forEach((section) => {
                section.classList.toggle("active", section.id === `tab-${target}`);
            });

            if (`tab-${target}` === workplacesTabId || `tab-${target}` === "tab-equipment") {
                scheduleResize();
                resizeHeatmaps();
                
                // Автоматически обновляем тепловую карту при открытии вкладки "Бронирование оборудования"
                if (`tab-${target}` === "tab-equipment") {
                    // Просто нажимаем кнопку "Показать занятость" после небольшой задержки
                    setTimeout(() => {
                        const heatmapDateInput = document.getElementById("heatmap-date");
                        const refreshHeatmapButton = document.getElementById("refresh-heatmap");
                        
                        // Если есть отложенное обновление (после отмены бронирования), используем эту дату
                        if (window._pendingHeatmapUpdateDate && heatmapDateInput) {
                            heatmapDateInput.value = window._pendingHeatmapUpdateDate;
                            delete window._pendingHeatmapUpdateDate;
                        }
                        
                        // Если дата не выбрана, устанавливаем сегодняшнюю дату
                        if (heatmapDateInput && !heatmapDateInput.value) {
                            const today = new Date().toISOString().split('T')[0];
                            heatmapDateInput.value = today;
                        }
                        
                        // Нажимаем кнопку "Показать занятость"
                        if (refreshHeatmapButton) {
                            refreshHeatmapButton.disabled = false;
                            refreshHeatmapButton.click();
                        }
                    }, 300);
                }
            }
            
            if (`tab-${target}` === "tab-manage-bookings") {
                // Загружаем данные только если не отключена автоматическая загрузка
                // (например, при переключении из календаря)
                if (!window._tempDisableAutoLoad) {
                    loadBookingsList();
                }
            }
            
            if (`tab-${target}` === "tab-calendar") {
                // Календарь загружается автоматически при активации вкладки
                const calendarMonthInput = document.getElementById("calendar-month");
                if (calendarMonthInput && calendarMonthInput.value) {
                    calendarMonthInput.dispatchEvent(new Event("change"));
                }
            }
            
            if (`tab-${target}` === "tab-si-module") {
                // Загружаем данные при активации вкладки СИ
                console.log("Активация вкладки СИ, загрузка данных...");
                loadEquipmentStats();
                const activeSubtab = document.querySelector("#tab-si-module .subtab-button.active");
                console.log("Активная подвкладка:", activeSubtab?.dataset.subtab);
                if (activeSubtab) {
                    const subtabType = activeSubtab.dataset.subtab === "gosregister" ? "gosregister" : activeSubtab.dataset.subtab;
                    console.log("Загрузка данных для подвкладки:", subtabType);
                    loadEquipmentData(subtabType);
                } else {
                    // Если нет активной подвкладки, загружаем первую (СИ)
                    console.log("Нет активной подвкладки, загружаем 'si'");
                    loadEquipmentData("si");
                }
            }
            
            if (`tab-${target}` === "tab-users-management") {
                loadUsersList();
            }
        });
    });

    // Проверяем активную вкладку по умолчанию
    const activeTab = document.querySelector(".tab-button.active");
    if (activeTab) {
        if (activeTab.dataset.tab === "workplaces" || activeTab.dataset.tab === "equipment") {
            scheduleResize();
            resizeHeatmaps();
        } else if (activeTab.dataset.tab === "si-module") {
            // Если вкладка СИ активна по умолчанию, загружаем данные
            loadEquipmentStats();
            const activeSubtab = document.querySelector(".subtab-button.active");
            if (activeSubtab) {
                const subtabType = activeSubtab.dataset.subtab === "gosregister" ? "gosregister" : activeSubtab.dataset.subtab;
                loadEquipmentData(subtabType);
            } else {
                loadEquipmentData("si");
            }
        }
    }
}

function initHistorySubtabs() {
    const buttons = document.querySelectorAll(".history-subtab-button");
    const contents = document.querySelectorAll(".history-subtab-content");

    buttons.forEach((button) => {
        button.addEventListener("click", () => {
            const target = button.dataset.subtab;

            buttons.forEach((btn) => btn.classList.toggle("active", btn === button));
            contents.forEach((content) => {
                content.classList.toggle("active", content.id === `subtab-${target}`);
            });

            // Загружаем данные для активной подвкладки
            if (target === "dashboard") {
                // Даш-борд уже загружается через initDashboard
                scheduleResize();
            } else if (target === "heatmap") {
                scheduleResize();
                resizeHeatmaps();
            } else if (target === "equipment-stats" || target === "user-stats" || 
                       target === "temporal-patterns" || target === "forecast" || 
                       target === "recommendations") {
                loadAdvancedAnalytics();
            }
        });
    });

    // Инициализируем настройку виджетов для дашборда
    initWidgetCustomizer();
}

function initHeatmap(options) {
    const {
        graphId,
        buttonId,
        dateInputId,
        errorId,
        updatedAtId,
        initialFigure,
        initialError,
        buttonText,
        maxDate,
        hideLegend = false,
        summaryConfig = null,
        initialSummary = null,
    } = options;

    const graphContainer = document.getElementById(graphId);
    const dateInput = document.getElementById(dateInputId);
    const refreshButton = document.getElementById(buttonId);
    const errorBox = document.getElementById(errorId);
    if (!graphContainer || !dateInput || !refreshButton || !errorBox) {
        return;
    }

    if (maxDate) {
        dateInput.max = maxDate;
    }

    const applyInitialFigure = (figureData) => {
        if (!figureData) {
            return;
        }
        const figure = JSON.parse(JSON.stringify(figureData));
        applyHeatmapLegend(figure, hideLegend);
        applyHeatmapSize(figure, graphContainer);
        Plotly.newPlot(graphContainer, figure.data, figure.layout, {responsive: true}).then(() => {
            resizeSingleHeatmap(graphContainer);
            // гарантируем корректные размеры после первичного рендеринга
            setTimeout(() => resizeSingleHeatmap(graphContainer), 150);
        });
    };

    if (initialFigure) {
        applyInitialFigure(initialFigure);
    } else if (initialError) {
        errorBox.textContent = initialError;
    }

    if (summaryConfig) {
        updateHeatmapSummary(summaryConfig, initialSummary);
    }

    // Создаем функцию обновления, доступную глобально
    const refreshHeatmapData = () => {
        const selectedDate = dateInput.value;
        if (!selectedDate) {
            errorBox.textContent = "Укажите дату.";
            return;
        }
        errorBox.textContent = "";
        refreshButton.disabled = true;
        refreshButton.textContent = "Обновление...";

        // Добавляем timestamp для обхода кэша браузера
        const cacheBuster = `&_t=${Date.now()}`;
        fetch(`/api/heatmap?selected_date=${selectedDate}${cacheBuster}`, {
            cache: 'no-cache',
            headers: {
                'Cache-Control': 'no-cache'
            }
        })
            .then((response) => response.json())
            .then((data) => {
                if (data.error) {
                    errorBox.textContent = data.error;
                    if (summaryConfig) {
                        updateHeatmapSummary(summaryConfig, null);
                    }
                    return;
                }
                if (data.figure_json) {
                    applyInitialFigure(JSON.parse(data.figure_json));
                }
                if (summaryConfig) {
                    updateHeatmapSummary(summaryConfig, data.summary || null);
                }
            })
            .catch(() => {
                errorBox.textContent = "Не удалось загрузить данные.";
            })
            .finally(() => {
                refreshButton.disabled = false;
                refreshButton.textContent = buttonText;
                if (updatedAtId) {
                    const updatedAtLabel = document.getElementById(updatedAtId);
                    if (updatedAtLabel) {
                        updatedAtLabel.textContent = new Date().toLocaleTimeString("ru-RU");
                    }
                }
            });
    };
    
    // Сохраняем функцию глобально для доступа из других мест
    if (graphId === "heatmap-graph") {
        window.refreshHeatmapData = refreshHeatmapData;
    }
    
    refreshButton.addEventListener("click", refreshHeatmapData);

    registerHeatmap(graphContainer);
}

function initBookingForm() {
    const categorySelect = document.getElementById("booking-category");
    const equipmentSelect = document.getElementById("booking-equipment");
    const startSelect = document.getElementById("booking-start-time");
    const durationSelect = document.getElementById("booking-duration");
    const submitButton = document.getElementById("booking-submit");
    const statusBox = document.getElementById("booking-status");
    const dateInput = document.getElementById("booking-date");
    if (!categorySelect || !equipmentSelect || !startSelect || !durationSelect || !submitButton || !statusBox || !dateInput) {
        return;
    }

    const state = {
        slots: [],
        stepMinutes: 30,
        slotMap: new Map(),
    };

    const setStatus = (message, type = "") => {
        statusBox.textContent = message || "";
        statusBox.classList.remove("error", "success");
        if (type) {
            statusBox.classList.add(type);
        }
    };

    const setSelectPlaceholder = (select, text) => {
        select.innerHTML = "";
        const option = document.createElement("option");
        option.value = "";
        option.textContent = text;
        select.appendChild(option);
    };

    const resetEquipmentSelect = (placeholder = "Сначала выберите категорию") => {
        equipmentSelect.disabled = true;
        setSelectPlaceholder(equipmentSelect, placeholder);
    };

    const resetStartSelect = (placeholder = "Нет доступных интервалов") => {
        startSelect.disabled = true;
        setSelectPlaceholder(startSelect, placeholder);
    };

    const resetDurationSelect = (placeholder = "Сначала выберите время начала") => {
        durationSelect.disabled = true;
        setSelectPlaceholder(durationSelect, placeholder);
        submitButton.disabled = true;
    };

    const loadCategories = async () => {
        categorySelect.disabled = true;
        setSelectPlaceholder(categorySelect, "Загрузка категорий...");
        try {
            const response = await fetch("/api/bookings/categories");
            if (!response.ok) {
                throw new Error("Не удалось загрузить категории");
            }
            const data = await response.json();
            categorySelect.innerHTML = "";
            const defaultOption = document.createElement("option");
            defaultOption.value = "";
            defaultOption.textContent = "Выберите категорию";
            categorySelect.appendChild(defaultOption);
            data.forEach((item) => {
                const option = document.createElement("option");
                option.value = item.id;
                option.textContent = item.name;
                categorySelect.appendChild(option);
            });
            categorySelect.disabled = false;
        } catch (error) {
            console.error("Ошибка загрузки категорий:", error);
            setStatus(error.message || "Ошибка загрузки категорий", "error");
            categorySelect.innerHTML = "";
            const option = document.createElement("option");
            option.value = "";
            option.textContent = "Категории недоступны";
            categorySelect.appendChild(option);
        }
    };

    const loadEquipment = async (categoryId) => {
        resetEquipmentSelect("Загрузка оборудования...");
        resetStartSelect();
        resetDurationSelect();
        if (!categoryId) {
            return;
        }
        try {
            const response = await fetch(`/api/bookings/equipment?category_id=${categoryId}`);
            if (!response.ok) {
                throw new Error("Не удалось загрузить оборудование");
            }
            const data = await response.json();
            equipmentSelect.innerHTML = "";
            const defaultOption = document.createElement("option");
            defaultOption.value = "";
            defaultOption.textContent = "Выберите оборудование";
            equipmentSelect.appendChild(defaultOption);
            data.forEach((item) => {
                const option = document.createElement("option");
                option.value = item.id;
                option.textContent = item.name;
                equipmentSelect.appendChild(option);
            });
            equipmentSelect.disabled = false;
        } catch (error) {
            console.error("Ошибка загрузки оборудования:", error);
            setStatus(error.message || "Ошибка загрузки оборудования", "error");
            resetEquipmentSelect("Оборудование недоступно");
        }
    };

    const loadSlots = async () => {
        const equipmentId = equipmentSelect.value;
        const selectedDate = dateInput.value;
        resetStartSelect("Нет доступных интервалов");
        resetDurationSelect();
        if (!equipmentId || !selectedDate) {
            return;
        }
        try {
            startSelect.disabled = true;
            const params = new URLSearchParams({
                equipment_id: equipmentId,
                selected_date: selectedDate,
            });
            const response = await fetch(`/api/bookings/slots?${params.toString()}`);
            if (!response.ok) {
                throw new Error("Не удалось загрузить доступные интервалы");
            }
            const data = await response.json();
            state.stepMinutes = data.step_minutes || 30;
            state.slots = Array.isArray(data.slots) ? data.slots : [];
            state.slotMap = new Map(state.slots.map((slot) => [slot.time, slot]));
            if (!state.slots.length) {
                setStatus("На выбранную дату нет свободных интервалов.", "error");
                resetStartSelect("Нет доступных интервалов");
                return;
            }
            startSelect.innerHTML = "";
            const defaultOption = document.createElement("option");
            defaultOption.value = "";
            defaultOption.textContent = "Выберите время начала";
            startSelect.appendChild(defaultOption);
            state.slots.forEach((slot) => {
                const option = document.createElement("option");
                option.value = slot.time;
                option.textContent = slot.time;
                startSelect.appendChild(option);
            });
            startSelect.disabled = false;
            setStatus("");
        } catch (error) {
            console.error("Ошибка загрузки интервалов:", error);
            setStatus(error.message || "Ошибка загрузки интервалов", "error");
        }
    };

    const updateDurationOptions = () => {
        const selectedTime = startSelect.value;
        if (!selectedTime) {
            resetDurationSelect();
            return;
        }
        const slot = state.slotMap.get(selectedTime);
        if (!slot || !slot.max_duration_minutes) {
            resetDurationSelect("Нет доступных длительностей");
            return;
        }
        const durations = [];
        for (let minutes = state.stepMinutes; minutes <= slot.max_duration_minutes; minutes += state.stepMinutes) {
            durations.push(minutes);
        }
        if (!durations.length) {
            resetDurationSelect("Нет доступных длительностей");
            return;
        }
        durationSelect.innerHTML = "";
        const defaultOption = document.createElement("option");
        defaultOption.value = "";
        defaultOption.textContent = "Выберите длительность";
        durationSelect.appendChild(defaultOption);
        durations.forEach((minutes) => {
            const option = document.createElement("option");
            option.value = String(minutes);
            option.textContent = formatDuration(minutes);
            durationSelect.appendChild(option);
        });
        durationSelect.disabled = false;
        submitButton.disabled = true;
    };

    const submitBooking = async () => {
        if (!currentUser) {
            setStatus("Войдите в систему для бронирования.", "error");
            return;
        }
        const payload = {
            equipment_id: Number(equipmentSelect.value),
            date: dateInput.value,
            start_time: startSelect.value,
            duration_minutes: Number(durationSelect.value),
        };
        if (!payload.equipment_id || !payload.date || !payload.start_time || !payload.duration_minutes) {
            setStatus("Заполните все поля для бронирования.", "error");
            return;
        }
        try {
            submitButton.disabled = true;
            submitButton.textContent = "Бронирование...";
            setStatus("");
            const response = await fetch("/api/bookings", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                body: JSON.stringify(payload),
            });
            const result = await response.json().catch(() => ({}));
            if (!response.ok) {
                if (response.status === 401) {
                    setStatus("Сессия истекла. Войдите снова.", "error");
                    currentUser = null;
                    applyAuthState();
                    return;
                }
                if (response.status === 409 && Array.isArray(result.conflicts)) {
                    const conflictsText = result.conflicts
                        .map((conflict) => `${conflict.user}: ${conflict.time_start}–${conflict.time_end}`)
                        .join("; ");
                    setStatus(`${result.error}. Пересечения: ${conflictsText}`, "error");
                    return;
                }
                throw new Error(result.error || "Не удалось создать бронирование");
            }
            setStatus(result.message || "Бронирование создано.", "success");
            
            // Обновляем тепловую карту для даты созданного бронирования
            if (payload.date) {
                const heatmapDateInput = document.getElementById("heatmap-date");
                const refreshHeatmapButton = document.getElementById("refresh-heatmap");
                
                if (heatmapDateInput && refreshHeatmapButton) {
                    // Если дата в тепловой карте совпадает с датой созданного бронирования, обновляем
                    if (heatmapDateInput.value === payload.date) {
                        refreshHeatmapButton.click();
                    }
                }
            }
            durationSelect.value = "";
            startSelect.value = "";
            submitButton.disabled = true;
            const refreshButton = document.getElementById("refresh-heatmap");
            if (refreshButton) {
                refreshButton.click();
            }
            await loadSlots();
        } catch (error) {
            console.error("Ошибка создания бронирования:", error);
            setStatus(error.message || "Ошибка создания бронирования", "error");
        } finally {
            submitButton.textContent = "Забронировать";
            submitButton.disabled = !durationSelect.value;
        }
    };

    categorySelect.addEventListener("change", (event) => {
        const categoryId = event.target.value;
        if (!categoryId) {
            resetEquipmentSelect();
            resetStartSelect();
            resetDurationSelect();
            return;
        }
        loadEquipment(categoryId);
    });

    equipmentSelect.addEventListener("change", () => {
        loadSlots();
    });

    if (dateInput) {
        dateInput.addEventListener("change", () => {
            if (equipmentSelect.value) {
                loadSlots();
            }
        });
    }

    startSelect.addEventListener("change", () => {
        updateDurationOptions();
    });

    durationSelect.addEventListener("change", () => {
        submitButton.disabled = !durationSelect.value;
    });

    submitButton.addEventListener("click", (event) => {
        event.preventDefault();
        submitBooking();
    });

    resetEquipmentSelect();
    resetStartSelect();
    resetDurationSelect();
    loadCategories();
}

function applyHeatmapLegend(figure, hideLegend) {
    if (!hideLegend || !figure) {
        return;
    }
    figure.layout = figure.layout || {};
    figure.layout.showlegend = false;
    if (Array.isArray(figure.data)) {
        figure.data.forEach((trace) => {
            if (hideLegend) {
                trace.showscale = false;
                if (trace.colorbar) {
                    trace.colorbar.title = "";
                    trace.colorbar.len = 0.0001;
                }
            }
        });
    }
}

const defaultHeatmapMargin = {l: 80, r: 20, t: 40, b: 40};

function applyHeatmapSize(figure, container) {
    figure.layout = figure.layout || {};
    figure.layout.margin = {...defaultHeatmapMargin, ...(figure.layout.margin || {})};
    const {width, height} = getHeatmapDimensions(
        container,
        figure?.data?.[0],
        figure.layout.margin,
    );
    figure.layout.width = width;
    figure.layout.height = height;
}

function registerHeatmap(container) {
    if (!container) {
        return;
    }
    heatmapContainers.add(container);
    resizeSingleHeatmap(container);
    if (!heatmapResizeAttached) {
        window.addEventListener("resize", resizeHeatmaps);
        heatmapResizeAttached = true;
    }
}

function updateHeatmapSummary(config, summary) {
    if (!config) {
        return;
    }
    const formatValue = (value) => {
        if (value === null || value === undefined) {
            return "—";
        }
        if (typeof value === "number") {
            return value.toLocaleString("ru-RU");
        }
        return String(value);
    };

    if (config.activeId) {
        const activeEl = document.getElementById(config.activeId);
        if (activeEl) {
            const value = summary ? summary.active_bookings : undefined;
            activeEl.textContent = formatValue(value);
        }
    }

    if (config.freeId) {
        const freeEl = document.getElementById(config.freeId);
        if (freeEl) {
            const value = summary ? summary.free_slots : undefined;
            freeEl.textContent = formatValue(value);
        }
    }
}

function formatDuration(minutes) {
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    const hh = hours.toString().padStart(2, "0");
    const mm = mins.toString().padStart(2, "0");
    return `${hh}:${mm}`;
}

function resizeHeatmaps() {
    heatmapContainers.forEach(resizeSingleHeatmap);
}

function resizeSingleHeatmap(container) {
    if (!container || !container.data || !container.data.length) {
        return;
    }
    const margin = {...defaultHeatmapMargin, ...(container.layout?.margin || {})};
    const {width, height} = getHeatmapDimensions(
        container,
        container.data[0],
        margin,
    );
    Plotly.relayout(container, {width, height, margin});
}

function getHeatmapBounds(container) {
    const section = container.closest(".heatmap-section");
    if (section) {
        const styles = window.getComputedStyle(section);
        const padding = parseFloat(styles.paddingLeft) + parseFloat(styles.paddingRight);
        const width = Math.max(section.clientWidth - padding, 400);
        return {width};
    }
    return {
        width: Math.max(container.clientWidth || window.innerWidth - 80, 400),
    };
}

function getHeatmapDimensions(container, trace, margin = defaultHeatmapMargin) {
    const {width} = getHeatmapBounds(container);
    const interiorWidth = Math.max(
        width - (margin?.l ?? 0) - (margin?.r ?? 0),
        200,
    );
    const columns =
        (Array.isArray(trace?.x) && trace.x.length) ||
        (Array.isArray(trace?.z) && trace.z[0] && trace.z[0].length) ||
        24;
    const rows =
        (Array.isArray(trace?.y) && trace.y.length) ||
        (Array.isArray(trace?.z) && trace.z.length) ||
        10;

    const cellWidth = columns ? interiorWidth / columns : interiorWidth;
    const interiorHeight = Math.max(cellWidth * rows, 200);
    const height = interiorHeight + (margin?.t ?? 0) + (margin?.b ?? 0);

    return {width, height};
}

function initDashboard() {
    const equipmentSelect = document.getElementById("dashboard-equipment");
    const startInput = document.getElementById("dashboard-start");
    const endInput = document.getElementById("dashboard-end");
    const targetInput = document.getElementById("dashboard-target");
    const applyButton = document.getElementById("dashboard-apply");
    const exportButton = document.getElementById("dashboard-export");
    const messageBox = document.getElementById("dashboard-message");
    if (!equipmentSelect || !startInput || !endInput || !targetInput || !applyButton) {
        return;
    }

    const setLoading = (state) => {
        applyButton.disabled = state;
        applyButton.textContent = state ? "Загрузка..." : "Обновить аналитику";
    };

    const fetchData = (payload, silent = false) => {
        if (!silent) {
            setLoading(true);
            messageBox.textContent = "";
        }
        fetch("/api/dashboard/data", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload),
        })
            .then((response) => {
                if (!response.ok) {
                    return response.json().then((data) => {
                        throw new Error(data.detail || "Ошибка загрузки");
                    });
                }
                return response.json();
            })
            .then((data) => {
                renderDashboard(data);
                latestDashboardPayload = data;
                latestDashboardFilters = {
                    equipment: payload.equipment,
                    start_date: payload.start_date,
                    end_date: payload.end_date,
                    target_load: payload.target_load,
                };
                if (data.message) {
                    messageBox.textContent = data.message;
                }
            })
            .catch((error) => {
                messageBox.textContent = error.message || "Не удалось получить данные.";
            })
            .finally(() => {
                if (!silent) {
                    setLoading(false);
                }
            });
    };

    fetch("/api/dashboard/init")
        .then((response) => {
            if (!response.ok) {
                throw new Error("Не удалось получить данные дашборда.");
            }
            return response.json();
        })
        .then((data) => {
            populateEquipmentSelect(equipmentSelect, data.equipment, data.defaults.equipment);
            startInput.min = data.dateRange.min;
            startInput.max = data.dateRange.max;
            endInput.min = data.dateRange.min;
            endInput.max = data.dateRange.max;
            startInput.value = data.defaults.start_date;
            endInput.value = data.defaults.end_date;
            targetInput.value = data.defaults.target_load;
            renderDashboard(data.payload);
            latestDashboardPayload = data.payload;
            latestDashboardFilters = {
                equipment: data.defaults.equipment,
                start_date: data.defaults.start_date,
                end_date: data.defaults.end_date,
                target_load: data.defaults.target_load,
            };
            if (data.payload.message) {
                messageBox.textContent = data.payload.message;
            }
        })
        .catch((error) => {
            messageBox.textContent = error.message;
        });

    applyButton.addEventListener("click", () => {
        const selectedEquipment = Array.from(equipmentSelect.selectedOptions).map((option) => option.value);
        const startDate = startInput.value;
        const endDate = endInput.value;
        const targetLoad = Number(targetInput.value) || 8;

        if (!selectedEquipment.length) {
            messageBox.textContent = "Выберите хотя бы один прибор.";
            return;
        }
        if (!startDate || !endDate) {
            messageBox.textContent = "Укажите период.";
            return;
        }

        fetchData(
            {
                equipment: selectedEquipment,
                start_date: startDate,
                end_date: endDate,
                target_load: targetLoad,
            },
            false,
        );
    });

    if (exportButton) {
        exportButton.addEventListener("click", () => {
            if (!latestDashboardPayload || !latestDashboardFilters) {
                messageBox.textContent = "Сначала обновите аналитику.";
                return;
            }
            downloadDashboardCsv(latestDashboardPayload, latestDashboardFilters);
        });
    }

    const dashboardExportExcelButton = document.getElementById("dashboard-export-excel");
    if (dashboardExportExcelButton) {
        dashboardExportExcelButton.addEventListener("click", () => {
            if (!latestDashboardPayload || !latestDashboardFilters) {
                alert("Сначала обновите аналитику");
                return;
            }
            downloadDashboardExcel(latestDashboardPayload, latestDashboardFilters);
        });
    }

}

function populateEquipmentSelect(select, options, selectedValues) {
    select.innerHTML = "";
    options.forEach((option) => {
        const opt = document.createElement("option");
        opt.value = option;
        opt.textContent = option;
        if (selectedValues.includes(option)) {
            opt.selected = true;
        }
        select.appendChild(opt);
    });
}

const registeredPlots = new Set();
let resizeScheduled = false;
const heatmapContainers = new Set();
let heatmapResizeAttached = false;

function renderDashboard(payload) {
    const relativeContainer = document.getElementById("dashboard-relative");
    const absoluteContainer = document.getElementById("dashboard-absolute");
    const utilization = document.getElementById("dashboard-utilization");
    const userTable = document.getElementById("dashboard-users");
    const equipmentTable = document.getElementById("dashboard-equipment-table");

    const options = {responsive: true};

    if (payload.relativeFigure && relativeContainer) {
        const fig = JSON.parse(payload.relativeFigure);
        enforceFullWidth(fig);
        Plotly.react(relativeContainer, fig.data, fig.layout, options).then(() => resizePlot(relativeContainer));
        registerPlot(relativeContainer);
    }
    if (payload.absoluteFigure && absoluteContainer) {
        const fig = JSON.parse(payload.absoluteFigure);
        enforceFullWidth(fig);
        Plotly.react(absoluteContainer, fig.data, fig.layout, options).then(() => resizePlot(absoluteContainer));
        registerPlot(absoluteContainer);
    }

    if (utilization) {
        utilization.textContent = payload.utilization || "—";
    }

    if (userTable) {
        userTable.innerHTML = payload.users
            .map((row) => `<tr><td>${row.name}</td><td>${row.hours.toFixed(2)}</td></tr>`)
            .join("");
    }

    if (equipmentTable) {
        equipmentTable.innerHTML = payload.equipmentSummary
            .map((row) => `<tr><td>${row.name}</td><td>${row.hours.toFixed(2)}</td></tr>`)
            .join("");
    }

    // Рендерим ключевые показатели, если они есть
    if (payload.insights) {
        renderDashboardInsights(payload);
    }

    // Применяем настройки виджетов
    const prefs = loadWidgetPrefs();
    applyWidgetPrefs(prefs);

    // гарантируем пересчёт уже после первичной отрисовки
    window.requestAnimationFrame(scheduleResize);
}

function enforceFullWidth(fig) {
    fig.layout = fig.layout || {};
    const defaultMargin = {l: 60, r: 120, t: 80, b: 60};
    fig.layout.margin = {...defaultMargin, ...(fig.layout.margin || {})};
    fig.layout.autosize = true;
}

function registerPlot(container) {
    if (!container) return;
    registeredPlots.add(container);
    resizePlot(container);
    if (!resizeScheduled) {
        window.addEventListener("resize", scheduleResize);
        resizeScheduled = true;
    }
}

function scheduleResize() {
    window.requestAnimationFrame(() => {
        registeredPlots.forEach(resizePlot);
        resizeHeatmaps();
    });
}

function getChartWidth(container) {
    const panel = container.closest(".dashboard-panel");
    if (panel) {
        const styles = window.getComputedStyle(panel);
        const padding = parseFloat(styles.paddingLeft) + parseFloat(styles.paddingRight);
        const safeGap = 40;
        return panel.clientWidth - padding - safeGap;
    }
    return (container.clientWidth || window.innerWidth - 80) - 40;
}

function resizePlot(container) {
    if (!container || !container.data) return;
    const width = getChartWidth(container);
    const height = Math.max(420, Math.min(window.innerHeight * 0.6, 720));
    Plotly.relayout(container, {
        width,
        height,
    });
}

// Расширенная аналитика
async function loadAdvancedAnalytics() {
    const today = new Date();
    const sixMonthsAgo = new Date(today);
    sixMonthsAgo.setMonth(sixMonthsAgo.getMonth() - 6);
    
    const startDate = sixMonthsAgo.toISOString().split('T')[0];
    const endDate = today.toISOString().split('T')[0];

    try {
        const response = await fetch("/api/dashboard/advanced", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify({
                start_date: startDate,
                end_date: endDate,
                equipment: [], // Без фильтрации по оборудованию для рекомендаций
            }),
        });

        if (!response.ok) {
            throw new Error("Не удалось загрузить расширенную аналитику");
        }

        const data = await response.json();
        
        // Проверяем, какая подвкладка активна
        const activeSubtab = document.querySelector(".history-subtab-button.active");
        if (!activeSubtab) return;

        const subtab = activeSubtab.dataset.subtab;
        
        if (subtab === "equipment-stats") {
            renderAdvancedEquipmentStats(data);
        } else if (subtab === "user-stats") {
            renderAdvancedStaffStats(data);
        } else if (subtab === "temporal-patterns") {
            renderTemporalPatterns(data);
        } else if (subtab === "forecast") {
            renderForecastBlock(data);
        } else if (subtab === "recommendations") {
            renderRecommendationsBlock(data);
        }
    } catch (error) {
        console.error("Ошибка загрузки расширенной аналитики:", error);
    }
}

function formatUserName(fullName) {
    if (!fullName) return "";
    const parts = fullName.trim().split(/\s+/);
    return parts.length > 0 ? parts[parts.length - 1] : fullName;
}

function renderAdvancedEquipmentStats(data) {
    const container = document.getElementById("equipment-stats-grid");
    if (!container || !data.equipment_stats) return;

    let html = "";

    // График топ оборудования
    if (data.equipment_stats.equipment_figure) {
        html += `<div class="advanced-card">
            <h3>Топ оборудования по использованию</h3>
            <div class="chart-container" id="equipment-stats-chart"></div>
        </div>`;
    }

    // Детальная статистика по оборудованию
    if (data.equipment_stats.equipment_detailed && data.equipment_stats.equipment_detailed.length > 0) {
        html += `<div class="advanced-card">
            <h3>Детальная статистика по оборудованию</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Оборудование</th><th>Часы</th><th>Бронирований</th><th>Средняя длительность</th><th>Загрузка, %</th></tr>
                    </thead>
                    <tbody>`;
        data.equipment_stats.equipment_detailed.forEach(eq => {
            html += `<tr>
                <td>${eq.name}</td>
                <td>${eq.hours.toFixed(2)}</td>
                <td>${eq.bookings_count}</td>
                <td>${eq.avg_duration.toFixed(2)} ч</td>
                <td>${eq.utilization_pct.toFixed(1)}%</td>
            </tr>`;
        });
        html += `</tbody></table></div></div>`;
    }

    // Статистика по оборудованию (полный список)
    if (data.equipment_stats.category_stats && data.equipment_stats.category_stats.length > 0) {
        html += `<div class="advanced-card">
            <h3>Использование оборудования</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Оборудование</th><th>Часы</th></tr>
                    </thead>
                    <tbody>`;
        data.equipment_stats.category_stats.forEach(eq => {
            html += `<tr><td>${eq.name}</td><td>${eq.hours.toFixed(2)}</td></tr>`;
        });
        html += `</tbody></table></div></div>`;
    }

    // Топ пользователей оборудования
    if (data.equipment_stats.equipment_detailed && data.equipment_stats.equipment_detailed.length > 0) {
        html += `<div class="advanced-card">
            <h3>Топ пользователей по оборудованию</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Оборудование</th><th>Пользователь</th><th>Часы</th></tr>
                    </thead>
                    <tbody>`;
        data.equipment_stats.equipment_detailed.forEach(eq => {
            if (eq.top_users && eq.top_users.length > 0) {
                eq.top_users.forEach((user, idx) => {
                    html += `<tr>
                        <td>${idx === 0 ? eq.name : ""}</td>
                        <td>${formatUserName(user.name)}</td>
                        <td>${user.hours.toFixed(2)}</td>
                    </tr>`;
                });
            }
        });
        html += `</tbody></table></div></div>`;
    }

    // График распределения по дням недели
    if (data.equipment_stats.weekday_figure && data.equipment_stats.weekday_figure !== "{}") {
        html += `<div class="advanced-card">
            <h3>Распределение использования по дням недели</h3>
            <div class="chart-container" id="equipment-weekday-chart"></div>
        </div>`;
    }

    // График пиковых часов
    if (data.equipment_stats.peak_hours_figure && data.equipment_stats.peak_hours_figure !== "{}") {
        html += `<div class="advanced-card">
            <h3>Пиковые часы использования</h3>
            <div class="chart-container" id="equipment-peak-hours-chart"></div>
        </div>`;
    }

    // График динамики использования
    if (data.equipment_stats.monthly_figure && data.equipment_stats.monthly_figure !== "{}") {
        html += `<div class="advanced-card">
            <h3>Динамика использования по месяцам</h3>
            <div class="chart-container" id="equipment-monthly-chart"></div>
        </div>`;
    }

    container.innerHTML = html;

    // Рендерим графики
    if (data.equipment_stats.equipment_figure) {
        const fig = JSON.parse(data.equipment_stats.equipment_figure);
        const chartContainer = document.getElementById("equipment-stats-chart");
        if (chartContainer) {
            const containerWidth = chartContainer.offsetWidth || 600;
            const containerHeight = chartContainer.offsetHeight || 400;
            fig.layout.width = containerWidth;
            fig.layout.height = containerHeight;
            Plotly.newPlot("equipment-stats-chart", fig.data, fig.layout, {responsive: true, useResizeHandler: true});
        }
    }

    if (data.equipment_stats.weekday_figure && data.equipment_stats.weekday_figure !== "{}") {
        const fig = JSON.parse(data.equipment_stats.weekday_figure);
        const chartContainer = document.getElementById("equipment-weekday-chart");
        if (chartContainer) {
            const containerWidth = chartContainer.offsetWidth || 600;
            const containerHeight = chartContainer.offsetHeight || 400;
            fig.layout.width = containerWidth;
            fig.layout.height = containerHeight;
            Plotly.newPlot("equipment-weekday-chart", fig.data, fig.layout, {responsive: true, useResizeHandler: true});
        }
    }

    if (data.equipment_stats.peak_hours_figure && data.equipment_stats.peak_hours_figure !== "{}") {
        const fig = JSON.parse(data.equipment_stats.peak_hours_figure);
        const chartContainer = document.getElementById("equipment-peak-hours-chart");
        if (chartContainer) {
            const containerWidth = chartContainer.offsetWidth || 600;
            const containerHeight = chartContainer.offsetHeight || 400;
            fig.layout.width = containerWidth;
            fig.layout.height = containerHeight;
            Plotly.newPlot("equipment-peak-hours-chart", fig.data, fig.layout, {responsive: true, useResizeHandler: true});
        }
    }

    if (data.equipment_stats.monthly_figure && data.equipment_stats.monthly_figure !== "{}") {
        const fig = JSON.parse(data.equipment_stats.monthly_figure);
        const chartContainer = document.getElementById("equipment-monthly-chart");
        if (chartContainer) {
            const containerWidth = chartContainer.offsetWidth || 600;
            const containerHeight = chartContainer.offsetHeight || 400;
            fig.layout.width = containerWidth;
            fig.layout.height = containerHeight;
            Plotly.newPlot("equipment-monthly-chart", fig.data, fig.layout, {responsive: true, useResizeHandler: true});
        }
    }
}

function renderAdvancedStaffStats(data) {
    const container = document.getElementById("user-stats-grid");
    if (!container || !data.user_stats) return;

    let html = "";

    // График топ пользователей
    if (data.user_stats.user_figure) {
        html += `<div class="advanced-card">
            <h3>Топ пользователей по использованию</h3>
            <div class="chart-container" id="user-stats-chart"></div>
        </div>`;
    }

    // Детальная статистика по пользователям
    if (data.user_stats.user_detailed && data.user_stats.user_detailed.length > 0) {
        html += `<div class="advanced-card">
            <h3>Детальная статистика по пользователям</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Пользователь</th><th>Часы</th><th>Бронирований</th><th>Средняя длительность</th><th>Разнообразие оборудования</th></tr>
                    </thead>
                    <tbody>`;
        data.user_stats.user_detailed.forEach(user => {
            html += `<tr>
                <td>${formatUserName(user.name)}</td>
                <td>${user.hours.toFixed(2)}</td>
                <td>${user.bookings_count}</td>
                <td>${user.avg_duration.toFixed(2)} ч</td>
                <td>${user.equipment_diversity}</td>
            </tr>`;
        });
        html += `</tbody></table></div></div>`;
    }

    // Таблица топ пользователей
    if (data.user_stats.top_users && data.user_stats.top_users.length > 0) {
        html += `<div class="advanced-card">
            <h3>Список пользователей</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Пользователь</th><th>Часы</th></tr>
                    </thead>
                    <tbody>`;
        data.user_stats.top_users.forEach(user => {
            const surname = formatUserName(user.name);
            html += `<tr><td>${surname}</td><td>${user.hours.toFixed(2)}</td></tr>`;
        });
        html += `</tbody></table></div></div>`;
    }

    // Часто используемое оборудование пользователями
    if (data.user_stats.user_detailed && data.user_stats.user_detailed.length > 0) {
        html += `<div class="advanced-card">
            <h3>Часто используемое оборудование</h3>
            <div class="table-wrapper">
                <table>
                    <thead>
                        <tr><th>Пользователь</th><th>Оборудование</th><th>Часы</th></tr>
                    </thead>
                    <tbody>`;
        data.user_stats.user_detailed.forEach(user => {
            if (user.frequent_equipment && user.frequent_equipment.length > 0) {
                user.frequent_equipment.forEach((eq, idx) => {
                    html += `<tr>
                        <td>${idx === 0 ? formatUserName(user.name) : ""}</td>
                        <td>${eq.name}</td>
                        <td>${eq.hours.toFixed(2)}</td>
                    </tr>`;
                });
            }
        });
        html += `</tbody></table></div></div>`;
    }

    // График распределения по дням недели
    if (data.user_stats.weekday_figure && data.user_stats.weekday_figure !== "{}") {
        html += `<div class="advanced-card">
            <h3>Распределение активности по дням недели</h3>
            <div class="chart-container" id="user-weekday-chart"></div>
        </div>`;
    }

    // График пиковых часов работы
    if (data.user_stats.peak_hours_figure && data.user_stats.peak_hours_figure !== "{}") {
        html += `<div class="advanced-card">
            <h3>Пиковые часы работы</h3>
            <div class="chart-container" id="user-peak-hours-chart"></div>
        </div>`;
    }

    // График динамики активности
    if (data.user_stats.monthly_figure && data.user_stats.monthly_figure !== "{}") {
        html += `<div class="advanced-card">
            <h3>Динамика активности по месяцам</h3>
            <div class="chart-container" id="user-monthly-chart"></div>
        </div>`;
    }

    container.innerHTML = html;

    // Рендерим графики
    if (data.user_stats.user_figure) {
        const fig = JSON.parse(data.user_stats.user_figure);
        const chartContainer = document.getElementById("user-stats-chart");
        if (chartContainer) {
            const containerWidth = chartContainer.offsetWidth || 600;
            const containerHeight = chartContainer.offsetHeight || 400;
            fig.layout.width = containerWidth;
            fig.layout.height = containerHeight;
            Plotly.newPlot("user-stats-chart", fig.data, fig.layout, {responsive: true, useResizeHandler: true});
        }
    }

    if (data.user_stats.weekday_figure && data.user_stats.weekday_figure !== "{}") {
        const fig = JSON.parse(data.user_stats.weekday_figure);
        const chartContainer = document.getElementById("user-weekday-chart");
        if (chartContainer) {
            const containerWidth = chartContainer.offsetWidth || 600;
            const containerHeight = chartContainer.offsetHeight || 400;
            fig.layout.width = containerWidth;
            fig.layout.height = containerHeight;
            Plotly.newPlot("user-weekday-chart", fig.data, fig.layout, {responsive: true, useResizeHandler: true});
        }
    }

    if (data.user_stats.peak_hours_figure && data.user_stats.peak_hours_figure !== "{}") {
        const fig = JSON.parse(data.user_stats.peak_hours_figure);
        const chartContainer = document.getElementById("user-peak-hours-chart");
        if (chartContainer) {
            const containerWidth = chartContainer.offsetWidth || 600;
            const containerHeight = chartContainer.offsetHeight || 400;
            fig.layout.width = containerWidth;
            fig.layout.height = containerHeight;
            Plotly.newPlot("user-peak-hours-chart", fig.data, fig.layout, {responsive: true, useResizeHandler: true});
        }
    }

    if (data.user_stats.monthly_figure && data.user_stats.monthly_figure !== "{}") {
        const fig = JSON.parse(data.user_stats.monthly_figure);
        const chartContainer = document.getElementById("user-monthly-chart");
        if (chartContainer) {
            const containerWidth = chartContainer.offsetWidth || 600;
            const containerHeight = chartContainer.offsetHeight || 400;
            fig.layout.width = containerWidth;
            fig.layout.height = containerHeight;
            Plotly.newPlot("user-monthly-chart", fig.data, fig.layout, {responsive: true, useResizeHandler: true});
        }
    }
}

function renderTemporalPatterns(data) {
    const container = document.getElementById("temporal-patterns-grid");
    if (!container || !data.temporal_patterns) return;

    let html = "";

    // Почасовые паттерны
    if (data.temporal_patterns.hourly && data.temporal_patterns.hourly.figure) {
        html += `<div class="advanced-card">
            <h3>Использование по часам дня</h3>
            <div class="chart-container" id="hourly-patterns-chart"></div>
        </div>`;
    }

    // Недельные паттерны
    if (data.temporal_patterns.weekly && data.temporal_patterns.weekly.figure) {
        html += `<div class="advanced-card">
            <h3>Использование по дням недели</h3>
            <div class="chart-container" id="weekly-patterns-chart"></div>
        </div>`;
    }

    container.innerHTML = html;

    // Рендерим графики
    if (data.temporal_patterns.hourly && data.temporal_patterns.hourly.figure) {
        const fig = JSON.parse(data.temporal_patterns.hourly.figure);
        Plotly.newPlot("hourly-patterns-chart", fig.data, fig.layout, {responsive: true});
    }

    if (data.temporal_patterns.weekly && data.temporal_patterns.weekly.figure) {
        const fig = JSON.parse(data.temporal_patterns.weekly.figure);
        Plotly.newPlot("weekly-patterns-chart", fig.data, fig.layout, {responsive: true});
    }
}

function renderForecastBlock(data) {
    const container = document.getElementById("forecast-container");
    if (!container || !data.forecast) return;

    const forecast = data.forecast;
    let html = '<div class="chart-container" id="forecast-chart"></div>';
    
    if (forecast.legend && forecast.legend.length > 0) {
        html += '<div class="forecast-legend">';
        forecast.legend.forEach(item => {
            html += `<div class="forecast-legend-item">
                <div class="forecast-legend-color" style="background-color: ${item.color};"></div>
                <span>${item.label}</span>
            </div>`;
        });
        html += '</div>';
    }
    
    container.innerHTML = html;

    if (forecast.figure) {
        const fig = JSON.parse(forecast.figure);
        Plotly.newPlot("forecast-chart", fig.data, fig.layout, {responsive: true});
    }
}

function renderRecommendationsBlock(data) {
    if (!data.recommendations) return;

    const systemic = document.querySelector("#recommendations-systemic ul");
    const peak = document.querySelector("#recommendations-peak ul");
    const recent = document.querySelector("#recommendations-recent ul");

    if (systemic && data.recommendations.systemic) {
        systemic.innerHTML = data.recommendations.systemic.map(r => `<li>${r}</li>`).join("");
    }

    if (peak && data.recommendations.peak) {
        peak.innerHTML = data.recommendations.peak.map(r => `<li>${r}</li>`).join("");
    }

    if (recent && data.recommendations.recent) {
        recent.innerHTML = data.recommendations.recent.map(r => `<li>${r}</li>`).join("");
    }
}

// Настройка виджетов дашборда
const DASHBOARD_WIDGETS = [
    {id: "insights", label: "Ключевые показатели"},
    {id: "relative", label: "Относительная загрузка"},
    {id: "absolute", label: "Абсолютная загрузка"},
    {id: "users", label: "Список пользователей"},
    {id: "equipment", label: "Суммарная наработка"},
];

function getDefaultWidgetPrefs() {
    return DASHBOARD_WIDGETS.map(w => ({id: w.id, visible: true}));
}

function loadWidgetPrefs() {
    const stored = localStorage.getItem("dashboard-widget-prefs");
    if (!stored) return getDefaultWidgetPrefs();
    try {
        const parsed = JSON.parse(stored);
        return normalizeWidgetPrefs(parsed);
    } catch {
        return getDefaultWidgetPrefs();
    }
}

function normalizeWidgetPrefs(prefs) {
    const defaultIds = new Set(DASHBOARD_WIDGETS.map(w => w.id));
    const valid = prefs.filter(p => defaultIds.has(p.id));
    const missing = DASHBOARD_WIDGETS.filter(w => !valid.find(p => p.id === w.id));
    return [...valid, ...missing.map(w => ({id: w.id, visible: true}))];
}

function saveWidgetPrefs(prefs) {
    localStorage.setItem("dashboard-widget-prefs", JSON.stringify(prefs));
}

function applyWidgetPrefs(prefs) {
    const widgets = document.querySelectorAll(".dashboard-widget-card");
    widgets.forEach(widget => {
        const id = widget.dataset.widgetId;
        const pref = prefs.find(p => p.id === id);
        if (pref) {
            widget.style.display = pref.visible ? "block" : "none";
        }
    });
}

function initWidgetCustomizer() {
    const btn = document.getElementById("widget-customizer-btn");
    const modal = document.getElementById("widget-customizer");
    const closeBtn = document.getElementById("widget-customizer-close");
    const saveBtn = document.getElementById("widget-customizer-save");
    const resetBtn = document.getElementById("widget-customizer-reset");
    const list = document.getElementById("widget-list");

    if (!btn || !modal || !list) return;

    let currentPrefs = loadWidgetPrefs();

    function renderList() {
        list.innerHTML = "";
        currentPrefs.forEach((pref, index) => {
            const widget = DASHBOARD_WIDGETS.find(w => w.id === pref.id);
            if (!widget) return;

            const li = document.createElement("li");
            li.className = "widget-list-item";
            li.draggable = true;
            li.dataset.index = index;
            
            li.innerHTML = `
                <span class="widget-list-handle">☰</span>
                <input type="checkbox" id="widget-${pref.id}" ${pref.visible ? "checked" : ""}>
                <label for="widget-${pref.id}">${widget.label}</label>
            `;

            li.querySelector("input").addEventListener("change", (e) => {
                pref.visible = e.target.checked;
            });

            li.addEventListener("dragstart", (e) => {
                e.dataTransfer.setData("text/plain", index);
            });

            li.addEventListener("dragover", (e) => {
                e.preventDefault();
            });

            li.addEventListener("drop", (e) => {
                e.preventDefault();
                const fromIndex = parseInt(e.dataTransfer.getData("text/plain"));
                const toIndex = index;
                if (fromIndex !== toIndex) {
                    const [moved] = currentPrefs.splice(fromIndex, 1);
                    currentPrefs.splice(toIndex, 0, moved);
                    renderList();
                }
            });

            list.appendChild(li);
        });
    }

    btn.addEventListener("click", () => {
        currentPrefs = loadWidgetPrefs();
        renderList();
        modal.classList.add("active");
    });

    closeBtn?.addEventListener("click", () => {
        modal.classList.remove("active");
    });

    modal.querySelector(".widget-customizer-overlay")?.addEventListener("click", () => {
        modal.classList.remove("active");
    });

    saveBtn?.addEventListener("click", () => {
        saveWidgetPrefs(currentPrefs);
        applyWidgetPrefs(currentPrefs);
        modal.classList.remove("active");
    });

    resetBtn?.addEventListener("click", () => {
        currentPrefs = getDefaultWidgetPrefs();
        renderList();
    });

    // Применяем сохраненные настройки при загрузке
    applyWidgetPrefs(currentPrefs);
}

function renderDashboardInsights(data) {
    const container = document.getElementById("dashboard-insights");
    if (!container || !data.insights) return;

    let html = "";
    if (data.insights.topCategories) {
        html += `<div class="insight-card">
            <h4>Топ категорий по загрузке</h4>
            <ul>`;
        data.insights.topCategories.forEach(cat => {
            html += `<li>${cat.name}: ${cat.hours.toFixed(1)} ч</li>`;
        });
        html += `</ul></div>`;
    }
    if (data.insights.leadTime !== undefined) {
        html += `<div class="insight-card">
            <h4>Время подготовки</h4>
            <p>${data.insights.leadTime.toFixed(1)} ч</p>
        </div>`;
    }
    if (data.insights.weekendHolidayShare !== undefined) {
        html += `<div class="insight-card">
            <h4>Выходные и праздники</h4>
            <p>${(data.insights.weekendHolidayShare * 100).toFixed(1)}%</p>
        </div>`;
    }
    container.innerHTML = html;
}

// Модуль СИ (оборудование)
let equipmentData = {
    si: [],
    io: [],
    vo: [],
    gosregister: [],
};

const equipmentFilters = {
    si: {query: "", status: "all"},
    io: {query: "", status: "all"},
    vo: {query: "", status: "all"},
    gosregister: {query: "", status: "all"},
};

let currentSort = {
    column: null,
    direction: null,
};

function initEquipmentModule() {
    const siModuleTab = document.getElementById("tab-si-module");
    if (!siModuleTab) return;

    initEquipmentSubtabs();
    initEquipmentFilters();
    
    // Данные загружаются только при активации вкладки (см. initTabs)
    // Статистику можно загрузить сразу, но лучше при активации
}

function initCalendar() {
    const calendarMonthInput = document.getElementById("calendar-month");
    const calendarPrevBtn = document.getElementById("calendar-prev-month");
    const calendarNextBtn = document.getElementById("calendar-next-month");
    const calendarTodayBtn = document.getElementById("calendar-today");
    const calendarGrid = document.getElementById("calendar-grid");
    const calendarError = document.getElementById("calendar-error");

    if (!calendarMonthInput || !calendarGrid) {
        return;
    }

    // Устанавливаем текущий месяц по умолчанию
    const today = new Date();
    const currentYear = today.getFullYear();
    const currentMonth = String(today.getMonth() + 1).padStart(2, "0");
    calendarMonthInput.value = `${currentYear}-${currentMonth}`;

    // Загружаем календарь при изменении месяца
    const loadCalendar = async () => {
        const monthValue = calendarMonthInput.value;
        if (!monthValue) {
            return;
        }

        const [year, month] = monthValue.split("-").map(Number);
        if (!year || !month) {
            return;
        }

        calendarGrid.innerHTML = "<div>Загрузка...</div>";
        if (calendarError) {
            calendarError.classList.add("hidden");
            calendarError.textContent = "";
        }

        try {
            const response = await fetch(`/api/bookings/calendar?year=${year}&month=${month}`, {
                credentials: "include",
            });

            if (!response.ok) {
                throw new Error("Не удалось загрузить календарь");
            }

            const data = await response.json();
            if (data.error) {
                throw new Error(data.error);
            }

            renderCalendar(year, month, data.bookings || {});
        } catch (error) {
            console.error("Ошибка загрузки календаря:", error);
            if (calendarError) {
                calendarError.textContent = error.message || "Ошибка загрузки календаря";
                calendarError.classList.remove("hidden");
            }
            calendarGrid.innerHTML = "";
        }
    };

    // Рендеринг календаря
    const renderCalendar = (year, month, bookings) => {
        const firstDay = new Date(year, month - 1, 1);
        const lastDay = new Date(year, month, 0);
        const daysInMonth = lastDay.getDate();
        const startDayOfWeek = firstDay.getDay();
        const adjustedStartDay = startDayOfWeek === 0 ? 6 : startDayOfWeek - 1; // Понедельник = 0

        const weekDays = ["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"];
        let html = "";

        // Заголовки дней недели
        weekDays.forEach((day) => {
            html += `<div class="calendar-day-header">${day}</div>`;
        });

        // Пустые ячейки до начала месяца
        for (let i = 0; i < adjustedStartDay; i++) {
            const prevMonthDate = new Date(year, month - 1, -i);
            html += `<div class="calendar-day other-month"><span class="calendar-day-number">${prevMonthDate.getDate()}</span></div>`;
        }

        // Дни месяца
        const today = new Date();
        for (let day = 1; day <= daysInMonth; day++) {
            const date = new Date(year, month - 1, day);
            const dateStr = `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
            const bookingCount = bookings[dateStr] || 0;
            const isToday =
                date.getFullYear() === today.getFullYear() &&
                date.getMonth() === today.getMonth() &&
                date.getDate() === today.getDate();

            let dayClasses = "calendar-day";
            if (isToday) {
                dayClasses += " today";
            }
            if (bookingCount > 0) {
                dayClasses += " has-bookings";
            }

            html += `<div class="${dayClasses}" data-date="${dateStr}">
                <span class="calendar-day-number">${day}</span>
                ${bookingCount > 0 ? `<span class="calendar-day-count">${bookingCount}</span>` : ""}
            </div>`;
        }

        // Пустые ячейки после конца месяца
        const totalCells = adjustedStartDay + daysInMonth;
        const remainingCells = 7 - (totalCells % 7);
        if (remainingCells < 7) {
            for (let i = 1; i <= remainingCells; i++) {
                html += `<div class="calendar-day other-month"><span class="calendar-day-number">${i}</span></div>`;
            }
        }

        calendarGrid.innerHTML = html;

        // Обработчики кликов на дни
        calendarGrid.querySelectorAll(".calendar-day:not(.other-month)").forEach((dayEl) => {
            dayEl.addEventListener("click", () => {
                const dateStr = dayEl.dataset.date;
                if (!dateStr) {
                    return;
                }

                // Сохраняем дату для использования после переключения вкладки
                const targetDate = dateStr;
                
                // Переключаемся на вкладку "Управление бронированием"
                const manageBookingsTab = document.querySelector('.tab-button[data-tab="manage-bookings"]');
                if (manageBookingsTab) {
                    // Временно отключаем автоматическую загрузку при переключении вкладки
                    const originalLoadBookings = window._tempDisableAutoLoad;
                    window._tempDisableAutoLoad = true;
                    
                    manageBookingsTab.click();
                    
                    // Восстанавливаем через небольшую задержку
                    setTimeout(() => {
                        window._tempDisableAutoLoad = false;
                    }, 500);
                }

                // Устанавливаем дату и загружаем данные
                // Ждем, пока вкладка активируется и элементы появятся в DOM
                const setDateAndLoad = (targetDate) => {
                    const dateInput = document.getElementById("manage-booking-date");
                    if (dateInput) {
                        // Устанавливаем дату
                        dateInput.value = targetDate;
                        // Вызываем событие change для обновления значения
                        dateInput.dispatchEvent(new Event("change", { bubbles: true }));
                        
                        // Проверяем, что дата действительно установлена, и загружаем данные
                        if (typeof loadBookingsList === "function") {
                            // Вызываем с задержкой, чтобы дата точно установилась и DOM обновился
                            setTimeout(() => {
                                // Дополнительная проверка, что дата установлена
                                const currentDate = dateInput.value;
                                if (currentDate === targetDate) {
                                    loadBookingsList();
                                } else {
                                    // Если дата не установилась, пробуем еще раз
                                    dateInput.value = targetDate;
                                    setTimeout(() => {
                                        loadBookingsList();
                                    }, 100);
                                }
                            }, 300);
                        } else {
                            // Если функция еще не определена, нажимаем кнопку
                            const showBtn = document.getElementById("refresh-bookings");
                            if (showBtn) {
                                setTimeout(() => {
                                    showBtn.click();
                                }, 300);
                            }
                        }
                        return true;
                    }
                    return false;
                };

                // Пробуем сразу
                if (!setDateAndLoad(dateStr)) {
                    // Если не получилось, ждем и пробуем снова
                    setTimeout(() => {
                        if (!setDateAndLoad(dateStr)) {
                            // Последняя попытка
                            setTimeout(() => setDateAndLoad(dateStr), 400);
                        }
                    }, 300);
                }
            });
        });
    };

    // Обработчики событий
    calendarMonthInput.addEventListener("change", loadCalendar);
    if (calendarPrevBtn) {
        calendarPrevBtn.addEventListener("click", () => {
            const [year, month] = calendarMonthInput.value.split("-").map(Number);
            const prevMonth = month === 1 ? 12 : month - 1;
            const prevYear = month === 1 ? year - 1 : year;
            calendarMonthInput.value = `${prevYear}-${String(prevMonth).padStart(2, "0")}`;
            loadCalendar();
        });
    }
    if (calendarNextBtn) {
        calendarNextBtn.addEventListener("click", () => {
            const [year, month] = calendarMonthInput.value.split("-").map(Number);
            const nextMonth = month === 12 ? 1 : month + 1;
            const nextYear = month === 12 ? year + 1 : year;
            calendarMonthInput.value = `${nextYear}-${String(nextMonth).padStart(2, "0")}`;
            loadCalendar();
        });
    }
    if (calendarTodayBtn) {
        calendarTodayBtn.addEventListener("click", () => {
            const today = new Date();
            const currentYear = today.getFullYear();
            const currentMonth = String(today.getMonth() + 1).padStart(2, "0");
            calendarMonthInput.value = `${currentYear}-${currentMonth}`;
            loadCalendar();
        });
    }

    // Загружаем календарь при активации вкладки
    const calendarTab = document.querySelector('.tab-button[data-tab="calendar"]');
    if (calendarTab) {
        calendarTab.addEventListener("click", () => {
            loadCalendar();
        });
    }

    // Загружаем календарь при первой загрузке, если вкладка активна
    if (document.getElementById("tab-calendar")?.classList.contains("active")) {
        loadCalendar();
    }
}

function initEquipmentSubtabs() {
    const subtabButtons = document.querySelectorAll(".subtab-button");
    const subtabContents = document.querySelectorAll(".subtab-content");

    subtabButtons.forEach((button) => {
        button.addEventListener("click", () => {
            const targetSubtab = button.dataset.subtab;

            subtabButtons.forEach((btn) => btn.classList.toggle("active", btn === button));
            subtabContents.forEach((content) => {
                content.classList.toggle("active", content.id === `subtab-${targetSubtab}`);
            });

            const type = targetSubtab === "gosregister" ? "gosregister" : targetSubtab;
            if (equipmentData[type].length === 0) {
                loadEquipmentData(type);
            } else {
                renderEquipmentTable(type);
            }
        });
    });
}

function initEquipmentFilters() {
    const config = {
        si: {search: "si-search", status: "si-status-filter"},
        io: {search: "io-search", status: "io-status-filter"},
        vo: {search: "vo-search", status: "vo-status-filter"},
        gosregister: {search: "gosregister-search"},
    };

    Object.entries(config).forEach(([type, ids]) => {
        if (ids.search) {
            const input = document.getElementById(ids.search);
            if (input) {
                input.addEventListener("input", (event) => {
                    equipmentFilters[type].query = event.target.value || "";
                    renderEquipmentTable(type);
                });
            }
        }
        if (ids.status) {
            const select = document.getElementById(ids.status);
            if (select) {
                select.addEventListener("change", (event) => {
                    equipmentFilters[type].status = event.target.value || "all";
                    renderEquipmentTable(type);
                });
            }
        }
    });
}

async function loadEquipmentStats() {
    try {
        console.log("Загрузка статистики оборудования...");
        const response = await fetch("/api/equipment/stats");
        console.log("Ответ статистики:", response.status, response.statusText);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error("Ошибка API статистики:", errorData);
            throw new Error(errorData.detail || `Ошибка загрузки статистики: ${response.status}`);
        }
        const stats = await response.json();
        console.log("Получена статистика:", stats);
        console.log("Ключи в stats:", Object.keys(stats));

        // Проверяем существование элементов
        const siCountEl = document.getElementById("si-count");
        const ioCountEl = document.getElementById("io-count");
        const voCountEl = document.getElementById("vo-count");
        const gosregisterCountEl = document.getElementById("gosregister-count");
        
        if (!siCountEl || !ioCountEl || !voCountEl || !gosregisterCountEl) {
            console.error("Элементы для статистики не найдены в DOM!");
            return;
        }

        // Используем квадратные скобки для кириллических ключей
        const siCount = stats["си_count"] !== undefined ? stats["си_count"] : 0;
        const ioCount = stats["ио_count"] !== undefined ? stats["ио_count"] : 0;
        const voCount = stats["во_count"] !== undefined ? stats["во_count"] : 0;
        const gosregisterCount = stats.gosregister_count !== undefined ? stats.gosregister_count : 0;
        
        console.log("Устанавливаем значения:", { siCount, ioCount, voCount, gosregisterCount });
        
        siCountEl.textContent = siCount;
        ioCountEl.textContent = ioCount;
        voCountEl.textContent = voCount;
        gosregisterCountEl.textContent = gosregisterCount;
    } catch (error) {
        console.error("Ошибка загрузки статистики:", error);
        // Отображаем ошибку в счетчиках
        const errorText = "?";
        const siCountEl = document.getElementById("si-count");
        const ioCountEl = document.getElementById("io-count");
        const voCountEl = document.getElementById("vo-count");
        const gosregisterCountEl = document.getElementById("gosregister-count");
        if (siCountEl) siCountEl.textContent = errorText;
        if (ioCountEl) ioCountEl.textContent = errorText;
        if (voCountEl) voCountEl.textContent = errorText;
        if (gosregisterCountEl) gosregisterCountEl.textContent = errorText;
    }
}

async function loadEquipmentData(type) {
    try {
        let url;
        if (type === "gosregister") {
            url = "/api/equipment/gosregister";
        } else {
            // Маппинг типов: si -> СИ, io -> ИО, vo -> ВО
            const typeMap = {
                "si": "СИ",
                "io": "ИО",
                "vo": "ВО"
            };
            const equipmentType = typeMap[type] || type.toUpperCase();
            url = `/api/equipment/${equipmentType}`;
        }

        console.log(`Загрузка данных ${type} из ${url}`);
        const response = await fetch(url);
        console.log(`Ответ для ${type}:`, response.status, response.statusText);
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            console.error(`Ошибка API для ${type}:`, errorData);
            throw new Error(errorData.detail || `Ошибка загрузки данных ${type}: ${response.status}`);
        }
        const data = await response.json();
        console.log(`Получены данные для ${type}:`, data?.length || 0, "записей");
        console.log(`Первая запись для ${type}:`, data?.[0]);

        equipmentData[type] = Array.isArray(data) ? data : [];
        console.log(`Сохранено в equipmentData[${type}]:`, equipmentData[type].length, "записей");
        renderEquipmentTable(type);
        
        if (equipmentData[type].length === 0) {
            console.warn(`Нет данных для ${type} (массив пуст)`);
            const tbody = document.getElementById(`${type}-table-body`);
            if (tbody) {
                tbody.innerHTML = `<tr><td colspan="100%" style="text-align: center; color: #64748b; padding: 20px;">Нет данных для отображения</td></tr>`;
            }
        }
    } catch (error) {
        console.error(`Ошибка загрузки ${type}:`, error);
        const tbody = document.getElementById(`${type}-table-body`);
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="100%" style="text-align: center; color: #dc3545; padding: 20px;">Ошибка загрузки данных: ${error.message}</td></tr>`;
        }
    }
}

// Вспомогательные функции для рендеринга
function escapeHtml(text) {
    if (text === null || text === undefined) return "";
    const div = document.createElement("div");
    div.textContent = text;
    return div.innerHTML;
}

// Безопасное отображение текста с поддержкой <br> тегов
function safeHtml(text) {
    if (text === null || text === undefined) return "";
    const str = String(text);
    // Сначала заменяем <br> и <br/> на временный маркер
    const withMarker = str.replace(/<br\s*\/?>/gi, "___BR_TAG___");
    // Экранируем весь HTML
    const escaped = withMarker
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    // Возвращаем <br> теги обратно
    return escaped.replace(/___BR_TAG___/g, "<br>");
}

function formatDate(dateStr) {
    if (!dateStr) return "";
    try {
        const date = new Date(dateStr);
        return date.toLocaleDateString("ru-RU");
    } catch (e) {
        return dateStr;
    }
}

function renderEquipmentTable(type) {
    const tbody = document.getElementById(`${type}-table-body`);
    if (!tbody) {
        console.error(`Элемент #${type}-table-body не найден в DOM!`);
        return;
    }

    let data = equipmentData[type] || [];
    data = applyEquipmentFilters(type, data);
    console.log(`Рендеринг таблицы ${type}, записей: ${data.length}`);
    
    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="100%" style="text-align: center; color: #64748b; padding: 20px;">Нет данных для отображения</td></tr>`;
        return;
    }
    
    if (currentSort.column) {
        data = sortEquipmentData(data, currentSort.column, currentSort.direction);
    }

    try {
        tbody.innerHTML = data
            .map((row, index) => {
                try {
                    if (type === "si") {
                        return renderSIRow(row, index);
                    } else if (type === "io") {
                        return renderIORow(row, index);
                    } else if (type === "vo") {
                        return renderVORow(row, index);
                    } else if (type === "gosregister") {
                        return renderGosregisterRow(row, index);
                    }
                    return "";
                } catch (err) {
                    console.error(`Ошибка рендеринга строки ${index} для ${type}:`, err, row);
                    return "";
                }
            })
            .join("");
        console.log(`Таблица ${type} успешно отрендерена, строк: ${tbody.querySelectorAll("tr").length}`);
    } catch (error) {
        console.error(`Ошибка рендеринга таблицы ${type}:`, error);
        tbody.innerHTML = `<tr><td colspan="100%" style="text-align: center; color: #dc3545; padding: 20px;">Ошибка отображения данных: ${error.message}</td></tr>`;
    }

    // Добавляем обработчики сортировки
    document.querySelectorAll(`#subtab-${type} .sortable`).forEach((header) => {
        header.addEventListener("click", () => {
            const column = header.dataset.sort;
            handleEquipmentSort(type, column);
        });
    });
}

function applyEquipmentFilters(type, data) {
    const filters = equipmentFilters[type];
    if (!filters) {
        return data;
    }

    let filtered = data;
    const query = filters.query?.trim().toLowerCase();
    if (query) {
        filtered = filtered.filter((row) => getEquipmentSearchText(type, row).includes(query));
    }

    if (filters.status && filters.status !== "all" && type !== "gosregister") {
        filtered = filtered.filter((row) => getCalibrationStatus(row) === filters.status);
    }

    return filtered;
}

function getEquipmentSearchText(type, row) {
    const pieces = [];
    if (type === "si") {
        pieces.push(
            row.name,
            row.type_designation,
            row.serial_number,
            row.certificate_number,
            row.gosregister_number,
            row.manufacturer,
            row.note,
        );
    } else if (type === "io") {
        pieces.push(
            row.name,
            row.type_designation,
            row.serial_number,
            row.certificate_number,
            row.note,
        );
    } else if (type === "vo") {
        pieces.push(row.name, row.type_designation, row.serial_number, row.note);
    } else if (type === "gosregister") {
        pieces.push(row.gosregister_number, row.si_name, row.type_designation, row.manufacturer);
    }

    return pieces
        .filter((value) => value !== null && value !== undefined)
        .join(" ")
        .toLowerCase();
}

function getCalibrationStatus(row) {
    const rawValue = row?.days_until_calibration;
    if (rawValue === null || rawValue === undefined || rawValue === "") {
        return "no-data";
    }
    const days = Number(rawValue);
    if (!Number.isFinite(days)) {
        return "no-data";
    }
    if (days < 0) {
        return "overdue";
    }
    if (days <= 30) {
        return "soon";
    }
    return "normal";
}

function renderSIRow(row, index) {
    const daysUntil = row.days_until_calibration;
    let daysClass = "";
    let daysBadge = "";
    if (daysUntil !== null && daysUntil !== undefined) {
        if (daysUntil < 0) {
            daysClass = "badge-danger";
            daysBadge = "Просрочено";
        } else if (daysUntil <= 30) {
            daysClass = "badge-warning";
            daysBadge = `Осталось ${daysUntil} дн.`;
        } else {
            daysClass = "badge-success";
            daysBadge = `Осталось ${daysUntil} дн.`;
        }
    }

    // Формируем ссылку для свидетельства о поверке
    const certificateLink = row.certificate_url && row.certificate_number
        ? `<a href="${escapeHtml(row.certificate_url)}" target="_blank">${escapeHtml(row.certificate_number)}</a>`
        : escapeHtml(row.certificate_number || "");
    
    // Формируем ссылку для Госреестра
    const gosregisterLink = row.gosregister_url && row.gosregister_number
        ? `<a href="${escapeHtml(row.gosregister_url)}" target="_blank">${escapeHtml(row.gosregister_number)}</a>`
        : escapeHtml(row.gosregister_number || "");

    return `
        <tr>
            <td>${index + 1}</td>
            <td>${safeHtml(row.name || "")}</td>
            <td>${safeHtml(row.type_designation || "")}</td>
            <td>${escapeHtml(row.serial_number || "")}</td>
            <td>${certificateLink}</td>
            <td>${row.certificate_date ? formatDate(row.certificate_date) : ""}</td>
            <td>${row.next_calibration_date ? formatDate(row.next_calibration_date) : ""}</td>
            <td>${daysBadge ? `<span class="badge ${daysClass}">${daysBadge}</span>` : "—"}</td>
            <td>${gosregisterLink}</td>
            <td>${escapeHtml(row.calibration_cost || "")}</td>
            <td>${safeHtml(row.note || "")}</td>
        </tr>
    `;
}

function renderIORow(row, index) {
    const daysUntil = row.days_until_calibration;
    let daysClass = "";
    let daysBadge = "";
    if (daysUntil !== null && daysUntil !== undefined) {
        if (daysUntil < 0) {
            daysClass = "badge-danger";
            daysBadge = "Просрочено";
        } else if (daysUntil <= 30) {
            daysClass = "badge-warning";
            daysBadge = `Осталось ${daysUntil} дн.`;
        } else {
            daysClass = "badge-success";
            daysBadge = `Осталось ${daysUntil} дн.`;
        }
    }

    return `
        <tr>
            <td>${index + 1}</td>
            <td>${safeHtml(row.name || "")}</td>
            <td>${safeHtml(row.type_designation || "")}</td>
            <td>${escapeHtml(row.serial_number || "")}</td>
            <td>${escapeHtml(row.certificate_number || "")}</td>
            <td>${escapeHtml(row.mpi_priority || row.mpi || "")}</td>
            <td>${row.certificate_date ? formatDate(row.certificate_date) : ""}</td>
            <td>${row.next_calibration_date ? formatDate(row.next_calibration_date) : ""}</td>
            <td>${daysBadge ? `<span class="badge ${daysClass}">${daysBadge}</span>` : "—"}</td>
            <td>${escapeHtml(row.calibration_cost || "")}</td>
            <td>${safeHtml(row.note || "")}</td>
        </tr>
    `;
}

function renderVORow(row, index) {
    return `
        <tr>
            <td>${index + 1}</td>
            <td>${safeHtml(row.name || "")}</td>
            <td>${safeHtml(row.type_designation || "")}</td>
            <td>${escapeHtml(row.serial_number || "")}</td>
            <td>${safeHtml(row.note || "")}</td>
        </tr>
    `;
}

function renderGosregisterRow(row, index) {
    // Формируем ссылку для номера в Госреестре
    const gosregisterLink = row.web_url && row.gosregister_number
        ? `<a href="${escapeHtml(row.web_url)}" target="_blank">${escapeHtml(row.gosregister_number)}</a>`
        : escapeHtml(row.gosregister_number || "");
    
    return `
        <tr>
            <td>${index + 1}</td>
            <td>${gosregisterLink}</td>
            <td>${safeHtml(row.si_name || "")}</td>
            <td>${escapeHtml(row.type_designation || "")}</td>
            <td>${safeHtml(row.manufacturer || "")}</td>
        </tr>
    `;
}

function sortEquipmentData(data, column, direction) {
    return [...data].sort((a, b) => {
        let aVal = a[column];
        let bVal = b[column];

        if (column === "row_number") {
            aVal = parseInt(aVal) || 0;
            bVal = parseInt(bVal) || 0;
        } else if (column === "certificate_date" || column === "next_calibration_date") {
            aVal = aVal ? new Date(aVal) : new Date(0);
            bVal = bVal ? new Date(bVal) : new Date(0);
        } else if (column === "days_until_calibration" || column === "calibration_cost") {
            aVal = parseFloat(aVal) || 0;
            bVal = parseFloat(bVal) || 0;
        } else {
            aVal = (aVal || "").toString().toLowerCase();
            bVal = (bVal || "").toString().toLowerCase();
        }

        if (direction === "asc") {
            return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
        } else {
            return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
        }
    });
}

function handleEquipmentSort(type, column) {
    let direction = "asc";
    if (currentSort.column === column && currentSort.direction === "asc") {
        direction = "desc";
    }

    currentSort = {column, direction};

    // Обновляем индикаторы сортировки
    document.querySelectorAll(`#subtab-${type} .sortable`).forEach((header) => {
        header.classList.remove("sorted-asc", "sorted-desc");
    });

    const activeHeader = document.querySelector(`#subtab-${type} .sortable[data-sort="${column}"]`);
    if (activeHeader) {
        activeHeader.classList.add(direction === "asc" ? "sorted-asc" : "sorted-desc");
    }

    renderEquipmentTable(type);
}

// Функции для работы с модальными окнами
function openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.add("active");
        document.body.style.overflow = "hidden";
    }
}

function closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) {
        modal.classList.remove("active");
        document.body.style.overflow = "";
    }
}

// Инициализация модальных окон
function initModals() {
    // Закрытие по клику на фон
    document.querySelectorAll(".modal").forEach((modal) => {
        modal.addEventListener("click", (e) => {
            if (e.target === modal) {
                closeModal(modal.id);
            }
        });
    });

    // Закрытие по кнопкам
    document.querySelectorAll(".modal-close, [data-modal]").forEach((btn) => {
        btn.addEventListener("click", () => {
            const modalId = btn.dataset.modal || btn.closest(".modal")?.id;
            if (modalId) {
                closeModal(modalId);
            }
        });
    });

    // Кнопки "Добавить"
    document.querySelectorAll(".btn-add-equipment").forEach((btn) => {
        btn.addEventListener("click", () => {
            const type = btn.dataset.type;
            if (type === "si") {
                openModal("modal-add-si-select");
                loadGosregisterForSelect();
            } else if (type === "io") {
                openModal("modal-add-io");
            } else if (type === "vo") {
                openModal("modal-add-vo");
            } else if (type === "gosregister") {
                openModal("modal-add-gosregister");
            }
        });
    });
}

// Загрузка Госреестра для выбора СИ
async function loadGosregisterForSelect() {
    const select = document.getElementById("gosregister-select");
    if (!select) return;

    try {
        const response = await fetch("/api/equipment/gosregister");
        if (!response.ok) throw new Error("Ошибка загрузки Госреестра");
        const data = await response.json();

        select.innerHTML = "";
        if (data.length === 0) {
            select.innerHTML = '<option value="">Нет данных в Госреестре</option>';
            return;
        }

        data.forEach((item) => {
            const option = document.createElement("option");
            option.value = item.id;
            option.textContent = `${item.gosregister_number} - ${item.si_name}`;
            select.appendChild(option);
        });

        select.addEventListener("change", () => {
            const selectButton = document.getElementById("select-si-button");
            if (selectButton) {
                selectButton.disabled = !select.value;
            }
        });
    } catch (error) {
        console.error("Ошибка загрузки Госреестра:", error);
        select.innerHTML = '<option value="">Ошибка загрузки данных</option>';
    }
}

// Обработка выбора СИ из Госреестра
document.addEventListener("DOMContentLoaded", () => {
    const selectButton = document.getElementById("select-si-button");
    if (selectButton) {
        selectButton.addEventListener("click", () => {
            const select = document.getElementById("gosregister-select");
            if (!select || !select.value) return;

            const selectedOption = select.options[select.selectedIndex];
            const gosregisterId = select.value;

            // Загружаем данные выбранного СИ
            fetch("/api/equipment/gosregister")
                .then((res) => res.json())
                .then((data) => {
                    const selected = data.find((item) => item.id == gosregisterId);
                    if (selected) {
                        document.getElementById("selected-gosregister-number").textContent = selected.gosregister_number || "-";
                        document.getElementById("selected-si-name").textContent = selected.si_name || "-";
                        document.getElementById("selected-si-type").textContent = selected.type_designation || "-";
                        document.getElementById("selected-si-manufacturer").textContent = selected.manufacturer || "-";

                        // Сохраняем ID для формы
                        document.getElementById("add-si-form").dataset.gosregisterId = gosregisterId;

                        closeModal("modal-add-si-select");
                        openModal("modal-add-si-form");
                    }
                })
                .catch((error) => {
                    console.error("Ошибка загрузки данных СИ:", error);
                    alert("Ошибка загрузки данных выбранного СИ");
                });
        });
    }
});

// Обработка форм добавления
document.addEventListener("DOMContentLoaded", () => {
    // Форма добавления СИ
    const addSIButton = document.getElementById("add-si-button");
    if (addSIButton) {
        addSIButton.addEventListener("click", async () => {
            const form = document.getElementById("add-si-form");
            const gosregisterId = form.dataset.gosregisterId;
            if (!gosregisterId) {
                alert("Не выбран СИ из Госреестра");
                return;
            }

            const data = {
                gosregister_id: parseInt(gosregisterId),
                type: document.getElementById("si-type").value.trim(),
                serial_number: document.getElementById("si-serial-number").value.trim(),
                certificate_number: document.getElementById("si-certificate-number").value.trim() || null,
                calibration_date: document.getElementById("si-calibration-date").value || null,
            };

            if (!data.type || !data.serial_number) {
                alert("Заполните обязательные поля: Тип и Заводской номер");
                return;
            }

            try {
                addSIButton.disabled = true;
                addSIButton.textContent = "Добавление...";

                const response = await fetch("/api/equipment/add-si", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                });

                const result = await response.json().catch(() => ({}));

                if (!response.ok) {
                    if (response.status === 401) {
                        throw new Error("Требуется авторизация");
                    }
                    if (response.status === 403) {
                        throw new Error("Недостаточно прав");
                    }
                    throw new Error(result.error || "Ошибка добавления СИ");
                }

                alert(result.message || "СИ успешно добавлено");
                closeModal("modal-add-si-form");
                form.reset();
                form.removeAttribute("data-gosregister-id");

                // Перезагружаем данные
                loadEquipmentData("si");
                loadEquipmentStats();
            } catch (error) {
                console.error("Ошибка добавления СИ:", error);
                alert(error.message || "Ошибка при добавлении СИ");
            } finally {
                addSIButton.disabled = false;
                addSIButton.textContent = "Добавить СИ";
            }
        });
    }

    // Форма добавления ИО
    const addIOButton = document.getElementById("add-io-button");
    if (addIOButton) {
        addIOButton.addEventListener("click", async () => {
            const data = {
                name: document.getElementById("io-name").value.trim(),
                type: document.getElementById("io-type").value.trim(),
                serial_number: document.getElementById("io-serial-number").value.trim(),
                mpi: document.getElementById("io-mpi").value.trim() || "1 год",
                certificate_number: document.getElementById("io-certificate-number").value.trim() || null,
                certificate_date: document.getElementById("io-certificate-date").value || null,
                note: document.getElementById("io-note").value.trim() || null,
            };

            if (!data.name || !data.type || !data.serial_number) {
                alert("Заполните обязательные поля: Наименование, Обозначение типа и Зав. №");
                return;
            }

            try {
                addIOButton.disabled = true;
                addIOButton.textContent = "Добавление...";

                const response = await fetch("/api/equipment/add-io", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                });

                const result = await response.json().catch(() => ({}));

                if (!response.ok) {
                    if (response.status === 401) {
                        throw new Error("Требуется авторизация");
                    }
                    if (response.status === 403) {
                        throw new Error("Недостаточно прав");
                    }
                    throw new Error(result.error || "Ошибка добавления ИО");
                }

                alert(result.message || "ИО успешно добавлено");
                closeModal("modal-add-io");
                document.getElementById("add-io-form").reset();

                loadEquipmentData("io");
                loadEquipmentStats();
            } catch (error) {
                console.error("Ошибка добавления ИО:", error);
                alert(error.message || "Ошибка при добавлении ИО");
            } finally {
                addIOButton.disabled = false;
                addIOButton.textContent = "Внести данные в БД";
            }
        });
    }

    // Форма добавления ВО
    const addVOButton = document.getElementById("add-vo-button");
    if (addVOButton) {
        addVOButton.addEventListener("click", async () => {
            const data = {
                name: document.getElementById("vo-name").value.trim(),
                type: document.getElementById("vo-type").value.trim(),
                serial_number: document.getElementById("vo-serial-number").value.trim(),
                note: document.getElementById("vo-note").value.trim() || null,
            };

            if (!data.name || !data.type || !data.serial_number) {
                alert("Заполните обязательные поля: Наименование, Тип и Зав. №");
                return;
            }

            try {
                addVOButton.disabled = true;
                addVOButton.textContent = "Добавление...";

                const response = await fetch("/api/equipment/add-vo", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                });

                const result = await response.json().catch(() => ({}));

                if (!response.ok) {
                    if (response.status === 401) {
                        throw new Error("Требуется авторизация");
                    }
                    if (response.status === 403) {
                        throw new Error("Недостаточно прав");
                    }
                    throw new Error(result.error || "Ошибка добавления ВО");
                }

                alert(result.message || "ВО успешно добавлено");
                closeModal("modal-add-vo");
                document.getElementById("add-vo-form").reset();

                loadEquipmentData("vo");
                loadEquipmentStats();
            } catch (error) {
                console.error("Ошибка добавления ВО:", error);
                alert(error.message || "Ошибка при добавлении ВО");
            } finally {
                addVOButton.disabled = false;
                addVOButton.textContent = "Внести данные в БД";
            }
        });
    }

    // Форма добавления в Госреестр
    const addGosregisterButton = document.getElementById("add-gosregister-button");
    if (addGosregisterButton) {
        addGosregisterButton.addEventListener("click", async () => {
            const data = {
                gosregister_number: document.getElementById("gosregister-number").value.trim(),
                si_name: document.getElementById("gosregister-si-name").value.trim(),
                type_designation: document.getElementById("gosregister-type-designation").value.trim(),
                manufacturer: document.getElementById("gosregister-manufacturer").value.trim() || null,
                web_url: document.getElementById("gosregister-web-url").value.trim() || null,
            };

            if (!data.gosregister_number || !data.si_name || !data.type_designation) {
                alert("Заполните обязательные поля: Номер в Госреестре, Наименование СИ и Обозначение типа СИ");
                return;
            }

            try {
                addGosregisterButton.disabled = true;
                addGosregisterButton.textContent = "Добавление...";

                const response = await fetch("/api/equipment/add-gosregister", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(data),
                });

                const result = await response.json().catch(() => ({}));

                if (!response.ok) {
                    if (response.status === 401) {
                        throw new Error("Требуется авторизация");
                    }
                    if (response.status === 403) {
                        throw new Error("Недостаточно прав");
                    }
                    throw new Error(result.error || "Ошибка добавления в Госреестр");
                }

                alert(result.message || "Запись успешно добавлена в Госреестр");
                closeModal("modal-add-gosregister");
                document.getElementById("add-gosregister-form").reset();

                loadEquipmentData("gosregister");
                loadEquipmentStats();
            } catch (error) {
                console.error("Ошибка добавления в Госреестр:", error);
                alert(error.message || "Ошибка при добавлении в Госреестр");
            } finally {
                addGosregisterButton.disabled = false;
                addGosregisterButton.textContent = "Внести данные в БД";
            }
        });
    }

    // Инициализация модальных окон
    initModals();
});

async function initAuth() {
    const loginButton = document.getElementById("login-button");
    const logoutButton = document.getElementById("logout-button");

    if (loginButton) {
        loginButton.addEventListener("click", () => {
            window.location.href = "/login";
        });
    }

    if (logoutButton) {
        logoutButton.addEventListener("click", async () => {
            try {
                await fetch("/auth/logout", {method: "POST"});
            } catch (error) {
                console.error("Ошибка выхода:", error);
            } finally {
                currentUser = null;
                applyAuthState();
            }
        });
    }

    try {
        const response = await fetch("/auth/me", {credentials: "include"});
        if (response.ok) {
            currentUser = await response.json();
        } else {
            currentUser = null;
        }
    } catch (error) {
        currentUser = null;
    }

    applyAuthState();
}

function applyAuthState() {
    const loginButton = document.getElementById("login-button");
    const userInfo = document.getElementById("user-info");
    const userName = document.getElementById("user-name");
    const profileButton = document.getElementById("user-profile-button");

    if (currentUser) {
        if (loginButton) loginButton.classList.add("hidden");
        if (userInfo) userInfo.classList.remove("hidden");
        if (profileButton) profileButton.disabled = false;
        if (userName) {
            const nameParts = [currentUser.first_name, currentUser.last_name].filter(Boolean);
            userName.textContent = nameParts.join(" ") || "Пользователь";
        }
    } else {
        if (loginButton) loginButton.classList.remove("hidden");
        if (userInfo) userInfo.classList.add("hidden");
        if (profileButton) profileButton.disabled = true;
    }

    document.querySelectorAll(".requires-admin").forEach((element) => {
        if (currentUser?.is_admin) {
            element.classList.remove("hidden");
            if (typeof element.disabled !== "undefined") {
                element.disabled = false;
            }
        } else {
            element.classList.add("hidden");
            if (typeof element.disabled !== "undefined") {
                element.disabled = true;
            }
        }
    });

    // Скрываем вкладки, требующие авторизации, для неавторизованных пользователей
    const authTabButtons = document.querySelectorAll('.tab-button[data-requires-auth="true"]');
    const authTabContents = document.querySelectorAll('.tab-content[data-requires-auth="true"]');
    const requireAuthHidden = !currentUser;

    authTabButtons.forEach((button) => {
        if (requireAuthHidden) {
            button.classList.add("hidden");
        } else {
            button.classList.remove("hidden");
        }
    });

    authTabContents.forEach((content) => {
        if (requireAuthHidden) {
            content.classList.add("hidden");
        } else {
            content.classList.remove("hidden");
        }
    });

    // Если активна вкладка, требующая авторизации, и пользователь не авторизован - переключаем на первую доступную
    if (requireAuthHidden) {
        const activeButton = document.querySelector(".tab-button.active");
        if (activeButton && activeButton.dataset.requiresAuth === "true") {
            const fallback = document.querySelector('.tab-button:not(.hidden):not([data-requires-auth="true"])');
            if (fallback) {
                fallback.click();
            }
        }
    }

    // Показываем/скрываем вкладку управления пользователями для админов
    const usersManagementTab = document.querySelector('.tab-button[data-tab="users-management"]');
    if (usersManagementTab) {
        if (currentUser?.is_admin) {
            usersManagementTab.style.display = "";
        } else {
            usersManagementTab.style.display = "none";
        }
    }
}

function initManageBookings() {
    const dateInput = document.getElementById("manage-booking-date");
    const refreshButton = document.getElementById("refresh-bookings");
    const exportButton = document.getElementById("export-bookings");
    if (!dateInput || !refreshButton) {
        return;
    }

    refreshButton.addEventListener("click", () => {
        loadBookingsList();
    });

    if (exportButton) {
        exportButton.addEventListener("click", () => {
            const selectedDate = dateInput.value;
            if (!selectedDate) {
                alert("Укажите дату для экспорта.");
                return;
            }
            downloadBookingsCsv(selectedDate);
        });
    }

    const exportExcelButton = document.getElementById("export-bookings-excel");
    if (exportExcelButton) {
        exportExcelButton.addEventListener("click", () => {
            const selectedDate = dateInput.value;
            if (!selectedDate) {
                alert("Укажите дату для экспорта.");
                return;
            }
            downloadBookingsExcel(selectedDate);
        });
    }

    // Загружаем при первой активации вкладки
    const manageBookingsTab = document.getElementById("tab-manage-bookings");
    if (manageBookingsTab && manageBookingsTab.classList.contains("active")) {
        loadBookingsList();
    }
}

async function loadBookingsList() {
    const dateInput = document.getElementById("manage-booking-date");
    const loadingEl = document.getElementById("bookings-loading");
    const errorEl = document.getElementById("bookings-error");
    const tableEl = document.getElementById("bookings-table");
    const tableBody = document.getElementById("bookings-table-body");
    const emptyEl = document.getElementById("bookings-empty");
    const refreshButton = document.getElementById("refresh-bookings");

    if (!dateInput || !loadingEl || !errorEl || !tableEl || !tableBody || !emptyEl || !refreshButton) {
        return;
    }

    const selectedDate = dateInput.value;
    if (!selectedDate) {
        errorEl.textContent = "Укажите дату.";
        errorEl.style.display = "block";
        tableEl.style.display = "none";
        emptyEl.style.display = "none";
        loadingEl.style.display = "none";
        return;
    }

    loadingEl.style.display = "block";
    errorEl.style.display = "none";
    tableEl.style.display = "none";
    emptyEl.style.display = "none";
    refreshButton.disabled = true;
    refreshButton.textContent = "Обновление...";

    try {
        const isAdmin = currentUser?.is_admin || false;
        const endpoint = isAdmin ? "/api/bookings/all" : "/api/bookings/my";
        const url = `${endpoint}?selected_date=${selectedDate}`;
        
        const response = await fetch(url, {credentials: "include"});
        if (!response.ok) {
            if (response.status === 401) {
                throw new Error("Требуется авторизация. Пожалуйста, войдите в систему.");
            }
            if (response.status === 404) {
                throw new Error("Эндпоинт не найден. Проверьте подключение к серверу.");
            }
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || errorData.error || `Ошибка ${response.status}: Не удалось загрузить бронирования`);
        }

        const bookings = await response.json();
        tableBody.innerHTML = "";

        if (!bookings || bookings.length === 0) {
            emptyEl.style.display = "block";
            tableEl.style.display = "none";
        } else {
            tableEl.style.display = "table";
            emptyEl.style.display = "none";
            
            bookings.forEach((booking) => {
                const row = document.createElement("tr");
                const statusClass = booking.status === "Отменено" ? "status-cancelled" :
                                   booking.status === "Завершено" ? "status-finished" :
                                   booking.status === "Активное" ? "status-active" : "status-planned";
                
                // Форматирование даты в формат DD.MM.YYYY
                let formattedDate = "";
                if (booking.date) {
                    try {
                        const dateObj = new Date(booking.date);
                        if (!isNaN(dateObj.getTime())) {
                            const day = String(dateObj.getDate()).padStart(2, "0");
                            const month = String(dateObj.getMonth() + 1).padStart(2, "0");
                            const year = dateObj.getFullYear();
                            formattedDate = `${day}.${month}.${year}`;
                        } else {
                            formattedDate = booking.date;
                        }
                    } catch {
                        formattedDate = booking.date;
                    }
                }
                
                row.innerHTML = `
                    <td>${formattedDate}</td>
                    <td>${booking.equipment || ""}</td>
                    <td>${booking.time_interval || `${booking.time_start || ""} - ${booking.time_end || ""}`}</td>
                    <td>${booking.duration ? `${booking.duration.toFixed(1)} ч` : ""}</td>
                    <td><span class="status-badge ${statusClass}">${booking.status || ""}</span></td>
                    ${isAdmin ? `<td>${booking.user_name || ""}</td>` : ""}
                    <td>
                        ${booking.can_cancel ? `
                            <button class="btn-extend-booking" data-booking-id="${booking.id}">Продлить</button>
                            <button class="btn-cancel-booking" data-booking-id="${booking.id}">Отменить</button>
                        ` : ""}
                    </td>
                `;
                tableBody.appendChild(row);
            });

            // Обработчики кнопок продления и отмены
            tableBody.querySelectorAll(".btn-extend-booking").forEach((btn) => {
                btn.addEventListener("click", async (e) => {
                    const bookingId = parseInt(e.target.dataset.bookingId);
                    const extensionStr = prompt("На сколько продлить? Формат ЧЧ:ММ (например, 00:30, 01:00):", "00:30");
                    if (!extensionStr) return;
                    try {
                        const [hStr, mStr] = extensionStr.split(":");
                        const h = parseInt(hStr, 10);
                        const m = parseInt(mStr, 10);
                        if (Number.isNaN(h) || Number.isNaN(m) || h < 0 || m < 0) {
                            alert("Некорректный формат времени. Используйте ЧЧ:ММ.");
                            return;
                        }
                        const extensionMinutes = h * 60 + m;
                        if (extensionMinutes <= 0) {
                            alert("Длительность продления должна быть больше нуля.");
                            return;
                        }
                        await extendBooking(bookingId, extensionMinutes);
                    } catch (err) {
                        console.error("Ошибка парсинга времени продления:", err);
                        alert("Некорректный формат времени.");
                    }
                });
            });

            tableBody.querySelectorAll(".btn-cancel-booking").forEach((btn) => {
                btn.addEventListener("click", async (e) => {
                    const bookingId = parseInt(e.target.dataset.bookingId);
                    if (confirm("Вы уверены, что хотите отменить это бронирование?")) {
                        await cancelBooking(bookingId);
                    }
                });
            });
        }
    } catch (error) {
        console.error("Ошибка загрузки бронирований:", error);
        errorEl.textContent = error.message || "Не удалось загрузить бронирования";
        errorEl.style.display = "block";
        tableEl.style.display = "none";
        emptyEl.style.display = "none";
    } finally {
        loadingEl.style.display = "none";
        refreshButton.disabled = false;
        refreshButton.textContent = "Показать бронирования";
    }
}

async function downloadBookingsCsv(selectedDate) {
    const errorEl = document.getElementById("bookings-error");
    try {
        const params = new URLSearchParams();
        params.set("selected_date", selectedDate);
        if (currentUser?.is_admin) {
            params.set("scope", "all");
        }

        const response = await fetch(`/api/bookings/export?${params.toString()}`, {
            credentials: "include",
        });

        if (!response.ok) {
            let message = "Не удалось выгрузить бронирования";
            try {
                const errorData = await response.json();
                message = errorData.detail || errorData.error || message;
            } catch {
                // ignore
            }
            throw new Error(message);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `bookings_${selectedDate}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error("Ошибка экспорта бронирований:", error);
        if (errorEl) {
            errorEl.textContent = error.message || "Не удалось выгрузить бронирования";
            errorEl.style.display = "block";
        } else {
            alert(error.message || "Не удалось выгрузить бронирования");
        }
    }
}

function downloadDashboardCsv(payload, filters) {
    try {
        const lines = [];
        lines.push("Раздел;Значение");
        lines.push(`Начало периода;${filters.start_date || ""}`);
        lines.push(`Конец периода;${filters.end_date || ""}`);
        lines.push(`Оборудование;${(filters.equipment || []).join(", ")}`);
        lines.push(`Целевая загрузка (ч/день);${filters.target_load || ""}`);
        lines.push(`Фактическая загрузка;${payload.utilization || ""}`);
        lines.push("");

        lines.push("Суммарная наработка");
        lines.push("Прибор;Часы");
        (payload.equipmentSummary || []).forEach((row) => {
            lines.push(`${row.name || ""};${typeof row.hours === "number" ? row.hours.toFixed(2) : row.hours || ""}`);
        });
        lines.push("");

        lines.push("Активность пользователей");
        lines.push("Пользователь;Часы");
        (payload.users || []).forEach((row) => {
            lines.push(`${row.name || ""};${typeof row.hours === "number" ? row.hours.toFixed(2) : row.hours || ""}`);
        });

        const blob = new Blob([lines.join("\n")], {type: "text/csv;charset=utf-8"});
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        const start = filters.start_date ? filters.start_date.replaceAll("-", "") : "";
        const end = filters.end_date ? filters.end_date.replaceAll("-", "") : "";
        link.href = url;
        link.download = `dashboard_${start}_${end}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error("Ошибка экспорта аналитики:", error);
        alert(error.message || "Не удалось выгрузить аналитику");
    }
}

async function downloadBookingsExcel(selectedDate) {
    const errorEl = document.getElementById("bookings-error");
    try {
        const params = new URLSearchParams();
        params.set("selected_date", selectedDate);
        if (currentUser?.is_admin) {
            params.set("scope", "all");
        }

        const response = await fetch(`/api/bookings/export/excel?${params.toString()}`, {
            credentials: "include",
        });

        if (!response.ok) {
            let message = "Не удалось выгрузить бронирования";
            try {
                const errorData = await response.json();
                message = errorData.detail || errorData.error || message;
            } catch {
                // ignore
            }
            throw new Error(message);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `bookings_${selectedDate}.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error("Ошибка экспорта бронирований в Excel:", error);
        if (errorEl) {
            errorEl.textContent = error.message || "Не удалось выгрузить бронирования";
            errorEl.style.display = "block";
        } else {
            alert(error.message || "Не удалось выгрузить бронирования");
        }
    }
}

async function downloadDashboardExcel(payload, filters) {
    try {
        const response = await fetch("/api/dashboard/export/excel", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            credentials: "include",
            body: JSON.stringify({
                equipment: filters.equipment || [],
                start_date: filters.start_date || "",
                end_date: filters.end_date || "",
                target_load: filters.target_load || 8,
            }),
        });

        if (!response.ok) {
            let message = "Не удалось выгрузить аналитику";
            try {
                const errorData = await response.json();
                message = errorData.detail || errorData.error || message;
            } catch {
                // ignore
            }
            throw new Error(message);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        const start = filters.start_date ? filters.start_date.replaceAll("-", "") : "";
        const end = filters.end_date ? filters.end_date.replaceAll("-", "") : "";
        link.href = url;
        link.download = `dashboard_${start}_${end}.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error("Ошибка экспорта аналитики в Excel:", error);
        alert(error.message || "Не удалось выгрузить аналитику");
    }
}

async function downloadEquipmentExcel(equipmentType) {
    try {
        const response = await fetch(`/api/equipment/${equipmentType}/export/excel`, {
            credentials: "include",
        });

        if (!response.ok) {
            let message = "Не удалось выгрузить данные оборудования";
            try {
                const errorData = await response.json();
                message = errorData.detail || errorData.error || message;
            } catch {
                // ignore
            }
            throw new Error(message);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        const today = new Date().toISOString().split("T")[0].replaceAll("-", "");
        link.href = url;
        link.download = `equipment_${equipmentType}_${today}.xlsx`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error("Ошибка экспорта оборудования в Excel:", error);
        alert(error.message || "Не удалось выгрузить данные оборудования");
    }
}

async function downloadBookingsPdf(selectedDate) {
    const errorEl = document.getElementById("bookings-error");
    try {
        const params = new URLSearchParams();
        params.set("selected_date", selectedDate);
        if (currentUser?.is_admin) {
            params.set("scope", "all");
        }

        const response = await fetch(`/api/bookings/export/pdf?${params.toString()}`, {
            credentials: "include",
        });

        if (!response.ok) {
            let message = "Не удалось выгрузить бронирования";
            try {
                const errorData = await response.json();
                message = errorData.detail || errorData.error || message;
            } catch {
                // ignore
            }
            throw new Error(message);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `bookings_${selectedDate}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error("Ошибка экспорта бронирований в PDF:", error);
        if (errorEl) {
            errorEl.textContent = error.message || "Не удалось выгрузить бронирования";
            errorEl.style.display = "block";
        } else {
            alert(error.message || "Не удалось выгрузить бронирования");
        }
    }
}

// downloadDashboardPdf удалён: экспорт PDF для истории бронирований больше не используется

async function downloadEquipmentPdf(equipmentType) {
    try {
        const response = await fetch(`/api/equipment/${equipmentType}/export/pdf`, {
            credentials: "include",
        });

        if (!response.ok) {
            let message = "Не удалось выгрузить данные оборудования";
            try {
                const errorData = await response.json();
                message = errorData.detail || errorData.error || message;
            } catch {
                // ignore
            }
            throw new Error(message);
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        const today = new Date().toISOString().split("T")[0].replaceAll("-", "");
        link.href = url;
        link.download = `equipment_${equipmentType}_${today}.pdf`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);
    } catch (error) {
        console.error("Ошибка экспорта оборудования в PDF:", error);
        alert(error.message || "Не удалось выгрузить данные оборудования");
    }
}

async function cancelBooking(bookingId) {
    try {
        const response = await fetch(`/api/bookings/${bookingId}/cancel`, {
            method: "POST",
            credentials: "include",
        });

        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || "Не удалось отменить бронирование");
        }

        const result = await response.json();
        alert(result.message || "Бронирование отменено");
        
        // Перезагружаем список
        loadBookingsList();
        
        // Всегда обновляем тепловую карту при отмене бронирования
        if (result.data && result.data.date) {
            const cancelledDate = result.data.date;
            const heatmapDateInput = document.getElementById("heatmap-date");
            const refreshHeatmapButton = document.getElementById("refresh-heatmap");
            const bookingTab = document.getElementById("tab-equipment");
            
            if (heatmapDateInput && refreshHeatmapButton) {
                // Если вкладка "Бронирование оборудования" активна, обновляем сразу
                if (bookingTab && bookingTab.classList.contains("active")) {
                    // Устанавливаем дату отмененного бронирования, если она отличается
                    if (heatmapDateInput.value !== cancelledDate) {
                        heatmapDateInput.value = cancelledDate;
                    }
                    // Обновляем тепловую карту с небольшой задержкой
                    setTimeout(() => {
                        refreshHeatmapButton.click();
                    }, 100);
                } else {
                    // Если вкладка не активна, сохраняем дату для обновления при открытии
                    window._pendingHeatmapUpdateDate = cancelledDate;
                }
            }
        }
    } catch (error) {
        console.error("Ошибка отмены бронирования:", error);
        alert(error.message || "Не удалось отменить бронирование");
    }
}

async function extendBooking(bookingId, extensionMinutes) {
    const errorEl = document.getElementById("bookings-error");
    errorEl.style.display = "none";
    errorEl.textContent = "";
    try {
        const params = new URLSearchParams();
        params.set("extension_minutes", String(extensionMinutes));

        const response = await fetch(`/api/bookings/${bookingId}/extend?${params.toString()}`, {
            method: "POST",
            credentials: "include",
        });

        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            const message = data.detail || data.error || "Не удалось продлить бронирование";
            throw new Error(message);
        }

        const result = await response.json();
        const message = result.message || "Бронирование продлено";
        alert(message);

        // Перезагружаем список бронирований после успешного продления
        await loadUserBookings();
    } catch (error) {
        console.error("Ошибка продления бронирования:", error);
        errorEl.textContent = error.message || "Не удалось продлить бронирование";
        errorEl.style.display = "block";
    }
}

function initUserProfilePanel() {
    document.addEventListener("click", async (event) => {
        const trigger = event.target.closest("#user-profile-button");
        if (!trigger) return;
        event.preventDefault();
        if (!currentUser) {
            window.location.href = "/login";
            return;
        }
        await openUserProfileModal();
    });

    const saveButton = document.getElementById("user-profile-save");
    if (saveButton) {
        saveButton.addEventListener("click", handleUserProfileSave);
    }
}

async function openUserProfileModal() {
    const firstNameInput = document.getElementById("profile-first-name");
    const lastNameInput = document.getElementById("profile-last-name");
    const phoneInput = document.getElementById("profile-phone");
    const emailInput = document.getElementById("profile-email");
    const currentPwd = document.getElementById("current-password");
    const newPwd = document.getElementById("new-password");
    const confirmPwd = document.getElementById("confirm-password");
    const errorBox = document.getElementById("user-profile-error");

    if (!firstNameInput || !lastNameInput || !phoneInput || !emailInput || !errorBox) {
        return;
    }

    firstNameInput.value = currentUser?.first_name || "";
    lastNameInput.value = currentUser?.last_name || "";
    phoneInput.value = currentUser?.phone || "";
    emailInput.value = currentUser?.email || "";

    if (currentPwd) currentPwd.value = "";
    if (newPwd) newPwd.value = "";
    if (confirmPwd) confirmPwd.value = "";

    await loadNotificationSettings();

    errorBox.textContent = "";
    errorBox.classList.add("hidden");

    openModal("modal-user-profile");
}

async function handleUserProfileSave() {
    const saveBtn = document.getElementById("user-profile-save");
    const errorBox = document.getElementById("user-profile-error");
    const firstNameInput = document.getElementById("profile-first-name");
    const lastNameInput = document.getElementById("profile-last-name");
    const phoneInput = document.getElementById("profile-phone");
    const emailInput = document.getElementById("profile-email");
    const emailCheckbox = document.getElementById("email-notifications-checkbox");
    const smsCheckbox = document.getElementById("sms-notifications-checkbox");
    const currentPwd = document.getElementById("current-password");
    const newPwd = document.getElementById("new-password");
    const confirmPwd = document.getElementById("confirm-password");

    if (!saveBtn || !errorBox || !firstNameInput || !lastNameInput || !phoneInput || !emailInput || !currentUser) {
        return;
    }

    const profilePayload = {
        first_name: firstNameInput.value.trim(),
        last_name: lastNameInput.value.trim(),
        phone: phoneInput.value.trim() || null,
        email: emailInput.value.trim() || null,
    };

    if (!profilePayload.first_name || !profilePayload.last_name) {
        errorBox.textContent = "Имя и фамилия обязательны для заполнения.";
        errorBox.classList.remove("hidden");
        return;
    }

    const currentPassword = currentPwd?.value || "";
    const newPassword = newPwd?.value || "";
    const confirmPassword = confirmPwd?.value || "";

    if (newPassword || confirmPassword || currentPassword) {
        if (!currentPassword || !newPassword || !confirmPassword) {
            errorBox.textContent = "Для смены пароля заполните все поля.";
            errorBox.classList.remove("hidden");
            return;
        }
        if (newPassword.length < 8) {
            errorBox.textContent = "Новый пароль должен содержать минимум 8 символов.";
            errorBox.classList.remove("hidden");
            return;
        }
        if (newPassword !== confirmPassword) {
            errorBox.textContent = "Пароли не совпадают.";
            errorBox.classList.remove("hidden");
            return;
        }
    }

    errorBox.textContent = "";
    errorBox.classList.add("hidden");

    try {
        saveBtn.disabled = true;
        saveBtn.textContent = "Сохранение...";

        await updateProfileRequest(profilePayload);

        await updateNotificationSettingsInline({
            email_notifications: emailCheckbox ? emailCheckbox.checked : true,
            sms_notifications: smsCheckbox ? smsCheckbox.checked : false,
        });

        if (newPassword && currentPassword) {
            await changePasswordInline(currentPassword, newPassword);
        }

        await refreshCurrentUser();
        alert("Изменения сохранены");
        closeModal("modal-user-profile");
    } catch (error) {
        console.error("Ошибка сохранения профиля:", error);
        errorBox.textContent = error.message || "Не удалось сохранить изменения.";
        errorBox.classList.remove("hidden");
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = "Применить";
    }
}

async function updateProfileRequest(payload) {
    const response = await fetch("/auth/profile", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || result.error || "Не удалось обновить профиль");
    }
}

async function loadNotificationSettings() {
    try {
        const response = await fetch("/auth/notification-settings", {credentials: "include"});
        if (!response.ok) {
            throw new Error("Не удалось загрузить настройки");
        }

        const settings = await response.json();
        const emailCheckbox = document.getElementById("email-notifications-checkbox");
        const smsCheckbox = document.getElementById("sms-notifications-checkbox");

        if (emailCheckbox) {
            emailCheckbox.checked = settings.email_notifications !== false;
        }
        if (smsCheckbox) {
            smsCheckbox.checked = settings.sms_notifications === true;
        }
    } catch (error) {
        console.error("Ошибка загрузки настроек уведомлений:", error);
    }
}

async function updateNotificationSettingsInline(payload) {
    const response = await fetch("/auth/notification-settings", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        credentials: "include",
        body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || "Не удалось сохранить настройки уведомлений");
    }
}

async function changePasswordInline(currentPassword, newPassword) {
    const response = await fetch("/auth/change-password", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword,
        }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        throw new Error(result.detail || "Не удалось обновить пароль");
    }
}

async function refreshCurrentUser() {
    try {
        const response = await fetch("/auth/me", {credentials: "include"});
        if (response.ok) {
            currentUser = await response.json();
        } else {
            currentUser = null;
        }
    } catch {
        currentUser = null;
    }
    applyAuthState();
}

// Управление пользователями (только для админов)
function initUsersManagement() {
    const addUserButton = document.getElementById("add-user-button");
    if (addUserButton) {
        addUserButton.addEventListener("click", () => {
            openUserForm();
        });
    }

    const userForm = document.getElementById("user-form");
    const submitUserForm = document.getElementById("submit-user-form");
    if (userForm && submitUserForm) {
        submitUserForm.addEventListener("click", async () => {
            await saveUser();
        });
    }

    const resetPasswordForm = document.getElementById("reset-user-password-form");
    const submitResetPassword = document.getElementById("submit-reset-password");
    if (resetPasswordForm && submitResetPassword) {
        submitResetPassword.addEventListener("click", async () => {
            await resetUserPassword();
        });
    }
}

async function loadUsersList() {
    const loadingEl = document.getElementById("users-loading");
    const errorEl = document.getElementById("users-error");
    const tableEl = document.getElementById("users-table");
    const tableBody = document.getElementById("users-tbody");

    if (!loadingEl || !errorEl || !tableEl || !tableBody) {
        return;
    }

    loadingEl.style.display = "block";
    errorEl.style.display = "none";
    tableEl.style.display = "none";

    try {
        const response = await fetch("/api/users", {credentials: "include"});
        if (!response.ok) {
            if (response.status === 401) {
                throw new Error("Требуется авторизация");
            }
            if (response.status === 403) {
                throw new Error("Доступ запрещен. Требуются права администратора");
            }
            const errorData = await response.json().catch(() => ({}));
            throw new Error(errorData.detail || "Не удалось загрузить пользователей");
        }

        const users = await response.json();
        tableBody.innerHTML = "";

        if (!users || users.length === 0) {
            tableEl.style.display = "none";
        } else {
            tableEl.style.display = "table";
            users.forEach((user) => {
                const row = document.createElement("tr");
                row.innerHTML = `
                    <td>${user.id || ""}</td>
                    <td>${user.last_name || ""}</td>
                    <td>${user.first_name || ""}</td>
                    <td>${user.phone || ""}</td>
                    <td>${user.email || ""}</td>
                    <td>${user.is_admin ? "✓" : ""}</td>
                    <td>${user.is_blocked ? "✓" : ""}</td>
                    <td>
                        <button class="btn-edit-user btn-secondary" data-user-id="${user.id}">Редактировать</button>
                        <button class="btn-reset-password-user" data-user-id="${user.id}" data-user-name="${(user.first_name || "") + " " + (user.last_name || "")}">Сбросить пароль</button>
                        <button class="btn-delete-user" data-user-id="${user.id}">Удалить</button>
                    </td>
                `;
                tableBody.appendChild(row);
            });

            // Добавляем обработчики событий
            tableBody.querySelectorAll(".btn-edit-user").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const userId = parseInt(btn.dataset.userId);
                    openUserForm(userId);
                });
            });

            tableBody.querySelectorAll(".btn-reset-password-user").forEach((btn) => {
                btn.addEventListener("click", () => {
                    const userId = parseInt(btn.dataset.userId);
                    const userName = btn.dataset.userName;
                    openResetPasswordForm(userId, userName);
                });
            });

            tableBody.querySelectorAll(".btn-delete-user").forEach((btn) => {
                btn.addEventListener("click", async () => {
                    const userId = parseInt(btn.dataset.userId);
                    if (confirm(`Вы уверены, что хотите удалить пользователя с ID ${userId}?`)) {
                        await deleteUser(userId);
                    }
                });
            });
        }
    } catch (error) {
        console.error("Ошибка загрузки пользователей:", error);
        errorEl.textContent = error.message || "Не удалось загрузить пользователей";
        errorEl.style.display = "block";
        tableEl.style.display = "none";
    } finally {
        loadingEl.style.display = "none";
    }
}

async function openUserForm(userId = null) {
    const modal = document.getElementById("modal-user-form");
    const form = document.getElementById("user-form");
    const title = document.getElementById("modal-user-form-title");
    const passwordGroup = document.getElementById("user-form-password-group");
    const blockedGroup = document.getElementById("user-form-blocked-group");
    const formId = document.getElementById("user-form-id");

    if (!modal || !form || !title) {
        return;
    }

    form.reset();
    formId.value = userId || "";

    if (userId) {
        title.textContent = "Редактировать пользователя";
        passwordGroup.style.display = "none";
        blockedGroup.style.display = "block";

        try {
            const response = await fetch(`/api/users/${userId}`, {credentials: "include"});
            if (!response.ok) {
                throw new Error("Не удалось загрузить данные пользователя");
            }
            const user = await response.json();
            document.getElementById("user-form-first-name").value = user.first_name || "";
            document.getElementById("user-form-last-name").value = user.last_name || "";
            document.getElementById("user-form-phone").value = user.phone || "";
            document.getElementById("user-form-email").value = user.email || "";
            document.getElementById("user-form-is-admin").checked = user.is_admin || false;
            document.getElementById("user-form-is-blocked").checked = user.is_blocked || false;
        } catch (error) {
            alert(error.message || "Ошибка загрузки данных пользователя");
            return;
        }
    } else {
        title.textContent = "Добавить пользователя";
        passwordGroup.style.display = "block";
        blockedGroup.style.display = "none";
    }

    openModal("modal-user-form");
}

async function saveUser() {
    const form = document.getElementById("user-form");
    const submitBtn = document.getElementById("submit-user-form");
    const errorBox = document.getElementById("user-form-error");

    if (!form || !submitBtn || !errorBox) {
        return;
    }

    const userId = form.querySelector("#user-form-id").value;
    const firstName = form.querySelector("#user-form-first-name").value.trim();
    const lastName = form.querySelector("#user-form-last-name").value.trim();
    const phone = form.querySelector("#user-form-phone").value.trim() || null;
    const email = form.querySelector("#user-form-email").value.trim() || null;
    const password = form.querySelector("#user-form-password")?.value || null;
    const isAdmin = form.querySelector("#user-form-is-admin").checked;
    const isBlocked = form.querySelector("#user-form-is-blocked")?.checked || false;

    if (!firstName || !lastName) {
        errorBox.textContent = "Имя и фамилия обязательны";
        errorBox.classList.remove("hidden");
        return;
    }

    if (!phone && !email) {
        errorBox.textContent = "Необходимо указать телефон или email";
        errorBox.classList.remove("hidden");
        return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Сохранение...";
    errorBox.classList.add("hidden");

    try {
        let response;
        if (userId) {
            // Обновление
            response = await fetch(`/api/users/${userId}`, {
                method: "PUT",
                headers: {"Content-Type": "application/json"},
                credentials: "include",
                body: JSON.stringify({
                    first_name: firstName,
                    last_name: lastName,
                    phone: phone,
                    email: email,
                    is_admin: isAdmin,
                    is_blocked: isBlocked,
                }),
            });
        } else {
            // Создание
            if (!password || password.length < 6) {
                throw new Error("Пароль должен содержать минимум 6 символов");
            }
            response = await fetch("/api/users", {
                method: "POST",
                headers: {"Content-Type": "application/json"},
                credentials: "include",
                body: JSON.stringify({
                    first_name: firstName,
                    last_name: lastName,
                    phone: phone,
                    email: email,
                    password: password,
                    is_admin: isAdmin,
                }),
            });
        }

        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || "Не удалось сохранить пользователя");
        }

        alert(result.message || "Пользователь успешно сохранен");
        form.reset();
        closeModal("modal-user-form");
        await loadUsersList();
    } catch (error) {
        errorBox.textContent = error.message || "Ошибка сохранения пользователя";
        errorBox.classList.remove("hidden");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Сохранить";
    }
}

function openResetPasswordForm(userId, userName) {
    const modal = document.getElementById("modal-reset-user-password");
    const form = document.getElementById("reset-user-password-form");
    const userIdInput = document.getElementById("reset-password-user-id");
    const userNameSpan = document.getElementById("reset-password-user-name");

    if (!modal || !form || !userIdInput || !userNameSpan) {
        return;
    }

    form.reset();
    userIdInput.value = userId;
    userNameSpan.textContent = userName || `ID ${userId}`;
    openModal("modal-reset-user-password");
}

async function resetUserPassword() {
    const form = document.getElementById("reset-user-password-form");
    const submitBtn = document.getElementById("submit-reset-password");
    const errorBox = document.getElementById("reset-password-error");

    if (!form || !submitBtn || !errorBox) {
        return;
    }

    const userId = form.querySelector("#reset-password-user-id").value;
    const newPassword = form.querySelector("#reset-password-new").value;

    if (!newPassword || newPassword.length < 6) {
        errorBox.textContent = "Пароль должен содержать минимум 6 символов";
        errorBox.classList.remove("hidden");
        return;
    }

    submitBtn.disabled = true;
    submitBtn.textContent = "Изменение...";
    errorBox.classList.add("hidden");

    try {
        const response = await fetch(`/api/users/${userId}/reset-password`, {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            credentials: "include",
            body: JSON.stringify({
                new_password: newPassword,
            }),
        });

        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || "Не удалось изменить пароль");
        }

        alert(result.message || "Пароль успешно изменен");
        form.reset();
        closeModal("modal-reset-user-password");
    } catch (error) {
        errorBox.textContent = error.message || "Ошибка изменения пароля";
        errorBox.classList.remove("hidden");
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Изменить пароль";
    }
}

async function deleteUser(userId) {
    try {
        const response = await fetch(`/api/users/${userId}`, {
            method: "DELETE",
            credentials: "include",
        });

        const result = await response.json().catch(() => ({}));
        if (!response.ok) {
            throw new Error(result.detail || "Не удалось удалить пользователя");
        }

        alert(result.message || "Пользователь успешно удален");
        await loadUsersList();
    } catch (error) {
        alert(error.message || "Ошибка удаления пользователя");
    }
}


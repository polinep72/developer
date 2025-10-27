// Глобальные переменные для хранения данных
let siData = [];
let ioData = [];
let voData = [];
let gosregisterData = [];

// Переменные для сортировки
let currentSort = {
    column: null,
    direction: null
};

// Загрузка статистики
async function loadStats() {
    try {
        const response = await fetch('/api/stats');
        const stats = await response.json();
        
        document.getElementById('si-count').textContent = stats.си_count || 0;
        document.getElementById('io-count').textContent = stats.ио_count || 0;
        document.getElementById('vo-count').textContent = stats.во_count || 0;
        document.getElementById('gosregister-count').textContent = stats.gosregister_count || 0;
    } catch (error) {
        console.error('Ошибка загрузки статистики:', error);
    }
}

// Функции сортировки
function sortData(data, column, direction) {
    if (!data || !column) return data;
    
    console.log(`Сортировка по столбцу: ${column}, направление: ${direction}`);
    console.log('Пример данных:', data.slice(0, 2));
    
    return [...data].sort((a, b) => {
        let aVal = a[column];
        let bVal = b[column];
        
        // Обработка специальных случаев
        if (column === 'row_number') {
            aVal = parseInt(aVal) || 0;
            bVal = parseInt(bVal) || 0;
        } else if (column === 'certificate_date' || column === 'next_calibration_date') {
            aVal = aVal ? new Date(aVal) : new Date(0);
            bVal = bVal ? new Date(bVal) : new Date(0);
        } else if (column === 'days_until_calibration' || column === 'calibration_cost') {
            aVal = parseFloat(aVal) || 0;
            bVal = parseFloat(bVal) || 0;
        } else if (column === 'type_designation') {
            // Специальная обработка для обозначения типа
            aVal = (aVal || '').toString().toLowerCase();
            bVal = (bVal || '').toString().toLowerCase();
        } else {
            // Строковое сравнение
            aVal = (aVal || '').toString().toLowerCase();
            bVal = (bVal || '').toString().toLowerCase();
        }
        
        if (direction === 'asc') {
            return aVal < bVal ? -1 : aVal > bVal ? 1 : 0;
        } else {
            return aVal > bVal ? -1 : aVal < bVal ? 1 : 0;
        }
    });
}

function updateSortIndicators(activeTab, column, direction) {
    // Убираем все индикаторы сортировки
    document.querySelectorAll(`#${activeTab} .sortable-header`).forEach(header => {
        header.classList.remove('sorted-asc', 'sorted-desc');
    });
    
    // Добавляем индикатор к активному столбцу
    const activeHeader = document.querySelector(`#${activeTab} .sortable-header[data-sort="${column}"]`);
    if (activeHeader) {
        activeHeader.classList.add(direction === 'asc' ? 'sorted-asc' : 'sorted-desc');
    }
}

function handleSort(activeTab, column) {
    // Определяем направление сортировки
    let direction = 'asc';
    if (currentSort.column === column && currentSort.direction === 'asc') {
        direction = 'desc';
    }
    
    // Обновляем текущую сортировку
    currentSort = { column, direction };
    
    // Сортируем данные в зависимости от активной вкладки
    let dataToSort;
    let renderFunction;
    
    switch(activeTab) {
        case 'si':
            dataToSort = siData;
            renderFunction = renderSITable;
            break;
        case 'io':
            dataToSort = ioData;
            renderFunction = renderIOTable;
            break;
        case 'vo':
            dataToSort = voData;
            renderFunction = renderVOTable;
            break;
        case 'gosregister':
            dataToSort = gosregisterData;
            renderFunction = renderGosregisterTable;
            break;
        default:
            return;
    }
    
    // Сортируем данные и обновляем отображение
    const sortedData = sortData(dataToSort, column, direction);
    
    // Обновляем глобальные переменные
    switch(activeTab) {
        case 'si':
            siData = sortedData;
            break;
        case 'io':
            ioData = sortedData;
            break;
        case 'vo':
            voData = sortedData;
            break;
        case 'gosregister':
            gosregisterData = sortedData;
            break;
    }
    
    // Обновляем индикаторы и перерисовываем таблицу
    updateSortIndicators(activeTab, column, direction);
    renderFunction();
}

// Загрузка данных СИ
async function loadSIData() {
    try {
        const response = await fetch('/api/equipment/СИ');
        siData = await response.json();
        renderSITable();
    } catch (error) {
        console.error('Ошибка загрузки данных СИ:', error);
    }
}

// Загрузка данных ИО
async function loadIOData() {
    try {
        const response = await fetch('/api/equipment/ИО');
        ioData = await response.json();
        renderIOTable();
    } catch (error) {
        console.error('Ошибка загрузки данных ИО:', error);
    }
}

// Загрузка данных ВО
async function loadVOData() {
    try {
        const response = await fetch('/api/equipment/ВО');
        voData = await response.json();
        renderVOTable();
    } catch (error) {
        console.error('Ошибка загрузки данных ВО:', error);
    }
}

// Загрузка данных Госреестра
async function loadGosregisterData() {
    try {
        const response = await fetch('/api/gosregister');
        gosregisterData = await response.json();
        renderGosregisterTable();
    } catch (error) {
        console.error('Ошибка загрузки данных Госреестра:', error);
    }
}

// Функция для создания ссылки на сертификат
function createCertificateLink(certificateNumber, certificateUrl) {
    if (!certificateNumber) return '';
    
    if (certificateUrl && certificateUrl.trim() !== '') {
        return `<a href="${certificateUrl}" target="_blank" title="Открыть сертификат">${certificateNumber}</a>`;
    }
    
    return certificateNumber;
}

// Функция для создания ссылки на запись Госреестра
function createGosregisterLink(gosNumber, gosUrl) {
    if (!gosNumber) return '';
    if (gosUrl && gosUrl.trim() !== '') {
        return `<a href="${gosUrl}" target="_blank" title="Открыть запись в Госреестре">${gosNumber}</a>`;
    }
    return gosNumber;
}

// Отрисовка таблицы СИ
function renderSITable() {
    const tbody = document.getElementById('si-table-body');
    tbody.innerHTML = '';
    
    siData.forEach((item, index) => {
        const row = document.createElement('tr');
        
        // Определяем статус поверки
        const daysLeft = item.days_until_calibration || 0;
        let statusBadge = '';
        if (daysLeft > 30) {
            statusBadge = '<span class="badge badge-calibration">В норме</span> ' + daysLeft;
        } else if (daysLeft > 0) {
            statusBadge = '<span class="badge badge-warning">Скоро поверка</span> ' + daysLeft;
        } else {
            statusBadge = '<span class="badge badge-danger">ПРОСРОЧЕНО</span>';
        }
        
        row.innerHTML = `
            <td>${index + 1}</td>
            <td>${item.name || ''}</td>
            <td>${item.type_designation || ''}</td>
            <td>${item.serial_number || ''}</td>
            <td>${createCertificateLink(item.certificate_number, item.certificate_url)}</td>
            <td>${formatDate(item.certificate_date)}</td>
            <td>${formatDate(item.next_calibration_date)}</td>
            <td>${statusBadge}</td>
            <td>${createGosregisterLink(item.gosregister_number, item.gosregister_url)}</td>
            <td>${item.calibration_cost ? item.calibration_cost + ' ₽' : ''}</td>
            <td>${item.note || ''}</td>
        `;
        tbody.appendChild(row);
    });
}

// Отрисовка таблицы ИО
function renderIOTable() {
    const tbody = document.getElementById('io-table-body');
    tbody.innerHTML = '';
    
    ioData.forEach((item, index) => {
        const row = document.createElement('tr');
        
        // Определяем статус аттестации (для ИО используется то же поле что и для СИ)
        const daysLeft = item.days_until_calibration || 0;
        let statusBadge = '';
        if (daysLeft > 30) {
            statusBadge = '<span class="badge badge-calibration">В норме</span> ' + daysLeft;
        } else if (daysLeft > 0) {
            statusBadge = '<span class="badge badge-warning">Скоро аттестация</span> ' + daysLeft;
        } else {
            statusBadge = '<span class="badge badge-danger">ПРОСРОЧЕНО</span>';
        }
        
        row.innerHTML = `
            <td>${index + 1}</td>
            <td>${item.name || ''}</td>
            <td>${item.type_designation || ''}</td>
            <td>${item.serial_number || ''}</td>
            <td>${createCertificateLink(item.certificate_number, item.certificate_url)}</td>
            <td>${item.mpi || ''}</td>
            <td>${formatDate(item.certificate_date)}</td>
            <td>${formatDate(item.next_calibration_date)}</td>
            <td>${statusBadge}</td>
            <td>${item.calibration_cost ? item.calibration_cost + ' ₽' : ''}</td>
            <td>${item.note || ''}</td>
        `;
        tbody.appendChild(row);
    });
}

// Отрисовка таблицы ВО
function renderVOTable() {
    const tbody = document.getElementById('vo-table-body');
    tbody.innerHTML = '';
    
    voData.forEach((item, index) => {
        const row = document.createElement('tr');
        
        row.innerHTML = `
            <td>${index + 1}</td>
            <td>${item.name || ''}</td>
            <td>${item.type_designation || ''}</td>
            <td>${item.serial_number || ''}</td>
            <td>${item.note || ''}</td>
        `;
        tbody.appendChild(row);
    });
}

// Отрисовка таблицы Госреестра
function renderGosregisterTable() {
    const tbody = document.getElementById('gosregister-table-body');
    tbody.innerHTML = '';
    
    gosregisterData.forEach((item, index) => {
        const row = document.createElement('tr');
        
        row.innerHTML = `
            <td>${index + 1}</td>
            <td>${createGosregisterLink(item.gosregister_number, item.web_url)}</td>
            <td>${item.si_name || ''}</td>
            <td>${item.type_designation || ''}</td>
            <td>${item.manufacturer || ''}</td>
        `;
        tbody.appendChild(row);
    });
}

// Форматирование даты
function formatDate(dateString) {
    if (!dateString) return '';
    
    try {
        const date = new Date(dateString);
        if (isNaN(date.getTime())) return dateString;
        
        return date.toLocaleDateString('ru-RU', {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit'
        });
    } catch (error) {
        return dateString;
    }
}

// Обработчики событий для вкладок
document.addEventListener('DOMContentLoaded', function() {
    // Загружаем данные при инициализации
    loadStats();
    loadSIData();
    
    // Обработчики для вкладок
    const siTab = document.getElementById('si-tab');
    const ioTab = document.getElementById('io-tab');
    const voTab = document.getElementById('vo-tab');
    const gosregisterTab = document.getElementById('gosregister-tab');
    
    siTab.addEventListener('click', function() {
        if (siData.length === 0) {
            loadSIData();
        }
    });
    
    ioTab.addEventListener('click', function() {
        if (ioData.length === 0) {
            loadIOData();
        }
    });
    
    voTab.addEventListener('click', function() {
        if (voData.length === 0) {
            loadVOData();
        }
    });
    
    gosregisterTab.addEventListener('click', function() {
        if (gosregisterData.length === 0) {
            loadGosregisterData();
        }
    });
    
    // Обработчики для модального окна Госреестра
    document.getElementById('parseGosregisterBtn').addEventListener('click', parseGosregisterData);
    document.getElementById('addToDatabaseBtn').addEventListener('click', addToDatabase);
    
    // Обработчик Enter в поле ввода номера Госреестра
    document.getElementById('gosregisterNumber').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            parseGosregisterData();
        }
    });

    // Обработчики для модального окна добавления СИ
    document.getElementById('selectSIButton').addEventListener('click', selectSIFromGosregister);
    document.getElementById('addSIButton').addEventListener('click', addSIToEquipment);
    
    // Обработчик выбора СИ из списка
    document.getElementById('gosregisterSelect').addEventListener('change', function() {
        const selectBtn = document.getElementById('selectSIButton');
        selectBtn.disabled = !this.value;
    });

    // Загружаем список СИ из Госреестра при открытии модального окна
    document.getElementById('addSIModal').addEventListener('show.bs.modal', loadGosregisterForSelection);

    // Обработчики для модального окна добавления ВО
    document.getElementById('addVOButton').addEventListener('click', addVOToEquipment);
    
    // Обработчики для модального окна добавления ИО
    document.getElementById('addIOButton').addEventListener('click', addIOToEquipment);
    
    // Обработчики сортировки для всех таблиц
    document.addEventListener('click', function(e) {
        if (e.target.classList.contains('sortable-header')) {
            const column = e.target.getAttribute('data-sort');
            const tableContainer = e.target.closest('.tab-pane');
            const activeTab = tableContainer ? tableContainer.id : null;
            
            if (column && activeTab) {
                handleSort(activeTab, column);
            }
        }
    });

    // Обновляем данные каждые 5 минут
    setInterval(() => {
        loadStats();
        loadSIData();
        loadIOData();
        loadVOData();
        loadGosregisterData();
    }, 300000);
});

// Глобальная переменная для хранения распарсенных данных
let parsedGosregisterData = null;

// Функция парсинга данных Госреестра
async function parseGosregisterData() {
    const gosregisterNumber = document.getElementById('gosregisterNumber').value.trim();
    const parseBtn = document.getElementById('parseGosregisterBtn');
    const statusDiv = document.getElementById('parsingStatus');
    const previewDiv = document.getElementById('previewData');
    const addBtn = document.getElementById('addToDatabaseBtn');
    
    if (!gosregisterNumber) {
        alert('Введите номер Госреестра!');
        return;
    }
    
    // Скрываем предыдущие результаты
    previewDiv.classList.add('d-none');
    addBtn.classList.add('d-none');
    
    // Показываем индикатор загрузки
    parseBtn.disabled = true;
    parseBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Поиск...';
    statusDiv.classList.remove('d-none');
    
    try {
        const response = await fetch('/api/gosregister/parse', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                gosregister_number: gosregisterNumber
            })
        });
        
        const result = await response.json();
        
        if (response.ok) {
            // Успешно найдены данные
            parsedGosregisterData = result.parsed_data;
            
            // Показываем найденные данные
            document.getElementById('previewNumber').textContent = parsedGosregisterData.gosregister_number;
            document.getElementById('previewName').textContent = parsedGosregisterData.si_name;
            document.getElementById('previewType').textContent = parsedGosregisterData.type_designation;
            document.getElementById('previewManufacturer').textContent = parsedGosregisterData.manufacturer;
            document.getElementById('previewMpi').textContent = parsedGosregisterData.mpi || 'Не найден';
            document.getElementById('previewLink').href = parsedGosregisterData.web_url || '#';
            
            // Показываем предварительный просмотр и кнопку добавления
            previewDiv.classList.remove('d-none');
            addBtn.classList.remove('d-none');
            
            statusDiv.className = 'alert alert-success';
            statusDiv.innerHTML = '<i class="fas fa-check me-2"></i>' + result.message;
            
        } else {
            // Ошибка
            statusDiv.className = 'alert alert-danger';
            statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>' + result.error;
            parsedGosregisterData = null;
        }
        
    } catch (error) {
        console.error('Ошибка при парсинге:', error);
        statusDiv.className = 'alert alert-danger';
        statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>Ошибка при поиске данных';
        parsedGosregisterData = null;
    } finally {
        // Восстанавливаем кнопку
        parseBtn.disabled = false;
        parseBtn.innerHTML = '<i class="fas fa-search me-1"></i>Найти данные';
    }
}

// Функция добавления в базу данных
async function addToDatabase() {
    if (!parsedGosregisterData) {
        alert('Нет данных для добавления!');
        return;
    }
    
    const addBtn = document.getElementById('addToDatabaseBtn');
    const statusDiv = document.getElementById('parsingStatus');
    
    // Показываем индикатор загрузки
    addBtn.disabled = true;
    addBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Добавление...';
    
    try {
        const response = await fetch('/api/gosregister/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(parsedGosregisterData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            // Успешно добавлено
            statusDiv.className = 'alert alert-success';
            statusDiv.innerHTML = '<i class="fas fa-check me-2"></i>' + result.message;
            
            // Обновляем данные Госреестра
            await loadGosregisterData();
            await loadStats();
            
            // Очищаем форму
            document.getElementById('gosregisterNumber').value = '';
            document.getElementById('previewData').classList.add('d-none');
            addBtn.classList.add('d-none');
            parsedGosregisterData = null;
            
            // Закрываем модальное окно через 2 секунды
            setTimeout(() => {
                const modal = bootstrap.Modal.getInstance(document.getElementById('addGosregisterModal'));
                modal.hide();
                statusDiv.classList.add('d-none');
                statusDiv.className = 'alert alert-info d-none';
            }, 2000);
            
        } else {
            // Ошибка
            statusDiv.className = 'alert alert-danger';
            statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>' + result.error;
        }
        
    } catch (error) {
        console.error('Ошибка при добавлении:', error);
        statusDiv.className = 'alert alert-danger';
        statusDiv.innerHTML = '<i class="fas fa-exclamation-triangle me-2"></i>Ошибка при добавлении в базу данных';
    } finally {
        // Восстанавливаем кнопку
        addBtn.disabled = false;
        addBtn.innerHTML = '<i class="fas fa-database me-1"></i>Внести СИ в БД';
    }
}

// Глобальная переменная для хранения выбранного СИ из Госреестра
let selectedGosregisterSI = null;

// Функция загрузки списка СИ из Госреестра для выбора
async function loadGosregisterForSelection() {
    const select = document.getElementById('gosregisterSelect');
    select.innerHTML = '<option value="">Загрузка...</option>';
    
    try {
        const response = await fetch('/api/gosregister');
        const data = await response.json();
        
        if (response.ok) {
            select.innerHTML = '';
            
            if (data.length === 0) {
                select.innerHTML = '<option value="">Нет данных в Госреестре</option>';
                return;
            }
            
            data.forEach(item => {
                const option = document.createElement('option');
                option.value = item.id;
                option.textContent = `${item.gosregister_number} - ${item.si_name}`;
                option.dataset.gosregisterNumber = item.gosregister_number;
                option.dataset.siName = item.si_name;
                option.dataset.typeDesignation = item.type_designation;
                option.dataset.manufacturer = item.manufacturer;
                select.appendChild(option);
            });
        } else {
            select.innerHTML = '<option value="">Ошибка загрузки данных</option>';
        }
    } catch (error) {
        console.error('Ошибка при загрузке Госреестра:', error);
        select.innerHTML = '<option value="">Ошибка загрузки данных</option>';
    }
}

// Функция выбора СИ из Госреестра
function selectSIFromGosregister() {
    const select = document.getElementById('gosregisterSelect');
    const selectedOption = select.options[select.selectedIndex];
    
    if (!selectedOption.value) {
        alert('Выберите СИ из списка!');
        return;
    }
    
    // Сохраняем данные выбранного СИ
    selectedGosregisterSI = {
        id: selectedOption.value,
        gosregister_number: selectedOption.dataset.gosregisterNumber,
        si_name: selectedOption.dataset.siName,
        type_designation: selectedOption.dataset.typeDesignation,
        manufacturer: selectedOption.dataset.manufacturer
    };
    
    // Заполняем информацию о выбранном СИ
    document.getElementById('selectedGosregisterNumber').textContent = selectedGosregisterSI.gosregister_number;
    document.getElementById('selectedSIName').textContent = selectedGosregisterSI.si_name;
    document.getElementById('selectedSIType').textContent = selectedGosregisterSI.type_designation;
    document.getElementById('selectedSIManufacturer').textContent = selectedGosregisterSI.manufacturer;
    
    // Предзаполняем тип на основе данных из Госреестра
    document.getElementById('siType').value = selectedGosregisterSI.type_designation;
    
    // Закрываем первое модальное окно и открываем второе
    const addSIModal = bootstrap.Modal.getInstance(document.getElementById('addSIModal'));
    addSIModal.hide();
    
    // Небольшая задержка для плавного перехода
    setTimeout(() => {
        const addSIFormModal = new bootstrap.Modal(document.getElementById('addSIFormModal'));
        addSIFormModal.show();
    }, 300);
}

// Функция добавления СИ в оборудование
async function addSIToEquipment() {
    if (!selectedGosregisterSI) {
        alert('СИ не выбран!');
        return;
    }
    
    // Собираем данные из формы
    const formData = {
        gosregister_id: selectedGosregisterSI.id,
        type: document.getElementById('siType').value.trim(),
        serial_number: document.getElementById('siSerialNumber').value.trim(),
        certificate_number: document.getElementById('siCertificateNumber').value.trim(),
        calibration_date: document.getElementById('siCalibrationDate').value
    };
    
    // Валидация
    if (!formData.type) {
        alert('Укажите тип СИ!');
        return;
    }
    
    if (!formData.serial_number) {
        alert('Укажите заводской номер!');
        return;
    }
    
    const addBtn = document.getElementById('addSIButton');
    
    // Показываем индикатор загрузки
    addBtn.disabled = true;
    addBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Добавление...';
    
    try {
        const response = await fetch('/api/equipment/add-si', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            // Успешно добавлено
            alert(result.message);
            
            // Очищаем форму
            document.getElementById('addSIForm').reset();
            selectedGosregisterSI = null;
            
            // Обновляем данные СИ
            await loadSIData();
            await loadStats();
            
            // Закрываем модальное окно
            const addSIFormModal = bootstrap.Modal.getInstance(document.getElementById('addSIFormModal'));
            addSIFormModal.hide();
            
        } else {
            // Ошибка
            alert('Ошибка: ' + result.error);
        }
        
    } catch (error) {
        console.error('Ошибка при добавлении СИ:', error);
        alert('Ошибка при добавлении СИ');
    } finally {
        // Восстанавливаем кнопку
        addBtn.disabled = false;
        addBtn.innerHTML = '<i class="fas fa-save me-1"></i>Добавить СИ';
    }
}

// Функция добавления ВО в оборудование
async function addVOToEquipment() {
    // Собираем данные из формы
    const formData = {
        name: document.getElementById('voName').value.trim(),
        type: document.getElementById('voType').value.trim(),
        serial_number: document.getElementById('voSerialNumber').value.trim(),
        note: document.getElementById('voNote').value.trim()
    };
    
    // Валидация
    if (!formData.name) {
        alert('Укажите наименование оборудования!');
        return;
    }
    
    if (!formData.type) {
        alert('Укажите тип оборудования!');
        return;
    }
    
    if (!formData.serial_number) {
        alert('Укажите заводской номер!');
        return;
    }
    
    const addBtn = document.getElementById('addVOButton');
    
    // Показываем индикатор загрузки
    addBtn.disabled = true;
    addBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Добавление...';
    
    try {
        const response = await fetch('/api/equipment/add-vo', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            // Успешно добавлено
            alert(result.message);
            
            // Очищаем форму
            document.getElementById('addVOForm').reset();
            
            // Обновляем данные ВО
            await loadVOData();
            await loadStats();
            
            // Закрываем модальное окно
            const addVOModal = bootstrap.Modal.getInstance(document.getElementById('addVOModal'));
            addVOModal.hide();
            
        } else {
            // Ошибка
            alert('Ошибка: ' + result.error);
        }
        
    } catch (error) {
        console.error('Ошибка при добавлении ВО:', error);
        alert('Ошибка при добавлении ВО');
    } finally {
        // Восстанавливаем кнопку
        addBtn.disabled = false;
        addBtn.innerHTML = '<i class="fas fa-save me-1"></i>Внести данные в БД';
    }
}

// Добавление ИО в оборудование
async function addIOToEquipment() {
    // Собираем данные из формы
    const formData = {
        name: document.getElementById('ioName').value.trim(),
        type: document.getElementById('ioType').value.trim(),
        serial_number: document.getElementById('ioSerialNumber').value.trim(),
        mpi: document.getElementById('ioMpi').value.trim() || '1 год',
        certificate_number: document.getElementById('ioCertificateNumber').value.trim(),
        certificate_date: document.getElementById('ioCertificateDate').value,
        note: document.getElementById('ioNote').value.trim()
    };
    
    // Валидация обязательных полей
    if (!formData.name) {
        alert('Укажите наименование ИО!');
        return;
    }
    
    if (!formData.type) {
        alert('Укажите обозначение типа!');
        return;
    }
    
    if (!formData.serial_number) {
        alert('Укажите заводской номер!');
        return;
    }
    
    const addBtn = document.getElementById('addIOButton');
    
    // Показываем индикатор загрузки
    addBtn.disabled = true;
    addBtn.innerHTML = '<i class="fas fa-spinner fa-spin me-1"></i>Добавление...';
    
    try {
        const response = await fetch('/api/equipment/add-io', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(formData)
        });
        
        const result = await response.json();
        
        if (response.ok) {
            // Успешно добавлено
            alert(result.message);
            
            // Очищаем форму
            document.getElementById('addIOForm').reset();
            // Возвращаем значение по умолчанию для МПИ
            document.getElementById('ioMpi').value = '1 год';
            
            // Обновляем данные ИО
            await loadIOData();
            await loadStats();
            
            // Закрываем модальное окно
            const addIOModal = bootstrap.Modal.getInstance(document.getElementById('addIOModal'));
            addIOModal.hide();
            
        } else {
            // Ошибка
            alert('Ошибка: ' + result.error);
        }
        
    } catch (error) {
        console.error('Ошибка при добавлении ИО:', error);
        alert('Ошибка при добавлении ИО: ' + error.message);
    } finally {
        // Восстанавливаем кнопку
        addBtn.disabled = false;
        addBtn.innerHTML = '<i class="fas fa-save me-1"></i>Внести данные в БД';
    }
}

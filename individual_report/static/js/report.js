// static/js/report.js
// Индивидуальный отчёт - клиентская логика

const REPORT_META = {
    employeeName: window.REPORT_EMPLOYEE_NAME || '',
    employeeId: window.REPORT_EMPLOYEE_ID || '',
    schemaVersion: 'individual_review_v1',
    caseIds: window.REPORT_CASE_IDS || []
};

document.addEventListener('DOMContentLoaded', function() {
    // Проверка доступности Chart.js
    if (typeof Chart === 'undefined') {
        console.error('Chart.js не загружен!');
        return;
    }
    
    const hardLabels = window.REPORT_HARD_LABELS || [];
    const hardSelf = window.REPORT_HARD_SELF || [];
    const hardManager = window.REPORT_HARD_MANAGER || [];

    const blockLabels = window.REPORT_BLOCK_LABELS || [];
    const blockSelf = window.REPORT_BLOCK_SELF || [];
    const blockManager = window.REPORT_BLOCK_MANAGER || [];
    const blockColleagues = window.REPORT_BLOCK_COLLEAGUES || [];

    function nullToUndefined(arr) {
        return arr.map(v => (v === null ? undefined : v));
    }

    // Инициализация графика Hard Skills с проверкой элемента
    const hardChartEl = document.getElementById('hardChart');
    if (hardChartEl && hardLabels && hardLabels.length > 0) {
        const ctxHard = hardChartEl.getContext('2d');
        new Chart(ctxHard, {
            type: 'bar',
            data: {
                labels: hardLabels,
                datasets: [
                    {
                        label: 'Самооценка',
                        data: nullToUndefined(hardSelf),
                        backgroundColor: '#006FFF',
                        borderRadius: 4,
                        barPercentage: 0.6,
                    },
                    {
                        label: 'Руководитель',
                        data: nullToUndefined(hardManager),
                        backgroundColor: '#FF310C',
                        borderRadius: 4,
                        barPercentage: 0.6,
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + (context.raw !== undefined ? context.raw : 'нет данных');
                            }
                        }
                    }
                },
                scales: {
                    y: {
                        min: 0,
                        max: 4,
                        ticks: { stepSize: 1, beginAtZero: true },
                        grid: { color: '#e9ecef' }
                    },
                    x: {
                        grid: { display: false },
                        ticks: {
                            maxRotation: 0,
                            minRotation: 0,
                            font: { size: 13 }
                        }
                    }
                }
            }
        });
    } else {
        console.warn('График Hard Skills не создан: отсутствует элемент canvas или нет данных');
    }

    // Инициализация графика Soft Skills с проверкой элемента
    const softChartEl = document.getElementById('softBlockChart');
    if (softChartEl && blockLabels && blockLabels.length > 0) {
        const ctxSoft = softChartEl.getContext('2d');
        new Chart(ctxSoft, {
            type: 'radar',
            data: {
                labels: blockLabels,
                datasets: [
                    {
                        label: 'Самооценка',
                        data: nullToUndefined(blockSelf),
                        borderColor: '#006FFF',
                        backgroundColor: 'rgba(0, 111, 255, 0.15)',
                        pointBackgroundColor: '#006FFF',
                        pointBorderColor: '#fff',
                        borderWidth: 2,
                        pointStyle: 'rect',
                    },
                    {
                        label: 'Руководитель',
                        data: nullToUndefined(blockManager),
                        borderColor: '#FF310C',
                        backgroundColor: 'rgba(255, 49, 12, 0.12)',
                        pointBackgroundColor: '#FF310C',
                        pointBorderColor: '#fff',
                        borderWidth: 2,
                        pointStyle: 'rect',
                    },
                    {
                        label: 'Коллеги',
                        data: nullToUndefined(blockColleagues),
                        borderColor: '#50E3C2',
                        backgroundColor: 'rgba(80, 227, 194, 0.12)',
                        pointBackgroundColor: '#50E3C2',
                        pointBorderColor: '#fff',
                        borderWidth: 2,
                        pointStyle: 'rect',
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + (context.raw !== undefined ? context.raw : 'нет данных');
                            }
                        }
                    }
                },
                scales: {
                    r: {
                        min: 0,
                        max: 4,
                        ticks: {
                            stepSize: 1,
                            display: false,
                            backdropColor: 'transparent'
                        },
                        grid: { color: '#dee2e6' },
                        angleLines: { color: '#dee2e6' },
                        pointLabels: {
                            font: { size: 11, weight: 'bold' },
                            padding: 10,
                            wordWrap: true,
                            maxWidth: 180,
                        }
                    }
                },
                elements: {
                    line: {
                        tension: 0.2,
                        borderWidth: 2
                    }
                }
            }
        });
    } else {
        console.warn('График Soft Skills не создан: отсутствует элемент canvas или нет данных');
    }

    // Инициализация навигации с проверкой элементов
    const navItems = document.querySelectorAll('.nav-item');
    navItems.forEach(item => {
        item.addEventListener('click', function(e) {
            const targetId = this.getAttribute('data-target');
            if (!targetId) return;
            const targetEl = document.getElementById(targetId);
            if (!targetEl) return;
            e.preventDefault();
            const stickyNav = document.getElementById('stickyNav');
            if (!stickyNav) return;
            const navHeight = stickyNav.offsetHeight;
            const targetPosition = targetEl.getBoundingClientRect().top + window.pageYOffset - navHeight - 10;
            window.scrollTo({ top: targetPosition, behavior: 'smooth' });
        });
    });

    const sections = [
        document.getElementById('section-charts'),
        document.getElementById('section-recommendations'),
        document.getElementById('section-table'),
        document.getElementById('section-cases'),
        document.getElementById('section-performance'),
        document.getElementById('section-final')
    ].filter(el => el !== null);

    const navButtons = document.querySelectorAll('.nav-item');

    function updateActiveNav() {
        const stickyNav = document.getElementById('stickyNav');
        if (!stickyNav || sections.length === 0) return;
        const navHeight = stickyNav.offsetHeight;
        let activeId = sections[0]?.id || null;
        for (const section of sections) {
            const rect = section.getBoundingClientRect();
            if (rect.top <= navHeight + 10) {
                activeId = section.id;
            } else {
                break;
            }
        }
        navButtons.forEach(btn => {
            btn.classList.toggle('active', btn.getAttribute('data-target') === activeId);
        });
    }

    let ticking = false;
    window.addEventListener('scroll', function() {
        if (!ticking) {
            window.requestAnimationFrame(function() {
                updateActiveNav();
                ticking = false;
            });
            ticking = true;
        }
    });
    
    // Первичное обновление навигации с задержкой для гарантии загрузки
    setTimeout(updateActiveNav, 100);

    function computeGradeFromLevels(levels) {
        let total = 0;
        let count = 0;
        levels.forEach(level => {
            if (!level) return;
            let base = '';
            if (level.startsWith('Junior')) base = 'Junior';
            else if (level.startsWith('Middle')) base = 'Middle';
            else if (level.startsWith('Senior') || level === 'Lead') base = 'Senior';
            if (base === 'Junior') total += 1;
            else if (base === 'Middle') total += 2;
            else if (base === 'Senior') total += 3;
            count++;
        });
        if (count === 0) return null;
        if (total >= 12) return 'Senior';
        else if (total >= 8) return 'Middle';
        else if (total >= 5) return 'Junior';
        else return null;
    }

    function updateSummary() {
        const aiInputs = document.querySelectorAll('[id$="_ai_score"]');
        const aiLevels = [];
        aiInputs.forEach(inp => {
            const val = inp.value.trim();
            if (val) aiLevels.push(val);
        });
        const aiGrade = computeGradeFromLevels(aiLevels);
        const aiGradeEl = document.getElementById('aiGradeValue');
        if (aiGradeEl) {
            aiGradeEl.textContent = aiGrade || '—';
        }

        const levelSelects = document.querySelectorAll('select[id$="_level"]');
        const mgrLevels = [];
        levelSelects.forEach(sel => {
            const val = sel.value;
            if (val) mgrLevels.push(val);
        });
        const mgrGrade = computeGradeFromLevels(mgrLevels);
        const mgrGradeEl = document.getElementById('managerGradeValue');
        if (mgrGradeEl) {
            mgrGradeEl.textContent = mgrGrade || '—';
        }

        const taskScoreSelect = document.getElementById('current_task_score');
        const taskScore = taskScoreSelect ? taskScoreSelect.value : '';
        const taskScoreEl = document.getElementById('taskScoreValue');
        if (taskScoreEl) {
            taskScoreEl.textContent = taskScore || '—';
        }
    }

    updateSummary();

    document.querySelectorAll('select[id$="_level"], #current_task_score').forEach(el => {
        el.addEventListener('change', updateSummary);
    });
    document.querySelectorAll('[id$="_ai_score"]').forEach(el => {
        el.addEventListener('change', updateSummary);
    });
});

function showValidationErrors(errors) {
    const msgDiv = document.getElementById('validationMessage');
    const msgList = document.getElementById('validationList');
    if (!msgDiv || !msgList) return;
    
    msgList.replaceChildren();
    errors.forEach(errorText => {
        const item = document.createElement('li');
        item.textContent = errorText;
        msgList.appendChild(item);
    });
    msgDiv.style.display = 'block';
    msgDiv.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

function buildExportColumns(caseIds) {
    const columns = ['schema_version', 'employee_id', 'employee_name', 'submitted_at'];
    caseIds.forEach(caseId => {
        columns.push(
            `case_${caseId}_comment`,
            `case_${caseId}_level`,
            `case_${caseId}_ai_score`,
            `case_${caseId}_positive_patterns`
        );
    });
    columns.push(
        'current_goals',
        'current_task',
        'current_task_score',
        'goal_future',
        'future_task',
        'final_grade',
        'final_justification'
    );
    return columns;
}

// ===== ВАЛИДАЦИЯ =====
function validateAndSave() {
    document.querySelectorAll('.validation-error').forEach(el => el.classList.remove('validation-error'));
    const msgDiv = document.getElementById('validationMessage');
    const msgList = document.getElementById('validationList');
    if (msgList) {
        msgList.replaceChildren();
    }
    if (msgDiv) {
        msgDiv.style.display = 'none';
    }

    const errors = [];

    // Кейсы
    document.querySelectorAll('.case-block').forEach(block => {
        const comment = block.querySelector('textarea[id$="_comment"]');
        const level = block.querySelector('select[id$="_level"]');
        const caseId = block.querySelector('.case-title')?.textContent?.trim() || 'кейс';
        if (comment && !comment.value.trim()) {
            comment.classList.add('validation-error');
            errors.push(`Комментарий для ${caseId}`);
        }
        if (level && !level.value) {
            level.classList.add('validation-error');
            errors.push(`Уровень ответа для ${caseId}`);
        }
    });

    // Performance Review
    const currentGoals = document.getElementById('current_goals');
    const currentTask = document.getElementById('current_task');
    const currentTaskScore = document.getElementById('current_task_score');
    const goalFuture = document.getElementById('goal_future');
    const futureTask = document.getElementById('future_task');

    if (currentGoals && !currentGoals.value.trim()) {
        currentGoals.classList.add('validation-error');
        errors.push('Текущая цель');
    }
    if (currentTask && !currentTask.value.trim()) {
        currentTask.classList.add('validation-error');
        errors.push('Основные задачи (текущие)');
    }
    if (currentTaskScore && !currentTaskScore.value) {
        currentTaskScore.classList.add('validation-error');
        errors.push('Оценка выполнения текущих задач');
    }
    if (goalFuture && !goalFuture.value.trim()) {
        goalFuture.classList.add('validation-error');
        errors.push('Цель на следующие 6 месяцев');
    }
    if (futureTask && !futureTask.value.trim()) {
        futureTask.classList.add('validation-error');
        errors.push('Задачи на следующие 6 месяцев');
    }

    // Итоговая оценка
    const finalGrade = document.getElementById('final_grade');
    const finalJustification = document.getElementById('final_justification');

    if (finalGrade && !finalGrade.value) {
        finalGrade.classList.add('validation-error');
        errors.push('Итоговый грейд');
    }
    if (finalJustification && !finalJustification.value.trim()) {
        finalJustification.classList.add('validation-error');
        errors.push('Обоснование грейда');
    }

    if (errors.length > 0) {
        showValidationErrors(errors);
        return;
    }

    saveData();
}

function saveData() {
    const fields = document.querySelectorAll('[data-field]');
    const data = {};
    fields.forEach(el => {
        const field = el.getAttribute('data-field');
        if (el.tagName === 'SELECT' && el.multiple) {
            data[field] = Array.from(el.selectedOptions).map(opt => opt.value);
        } else {
            data[field] = el.value;
        }
    });
    data['employee_name'] = REPORT_META.employeeName;
    data['employee_id'] = REPORT_META.employeeId;
    data['date'] = new Date().toLocaleString('ru-RU', { hour12: false });

    const columns = buildExportColumns(REPORT_META.caseIds);

    const row = columns.map(col => {
        let val = data[col];
        if (val === undefined || val === null) val = '';
        if (Array.isArray(val)) val = val.join(', ');
        return val;
    });

    try {
        const wb = XLSX.utils.book_new();
        const wsData = [columns, row];
        const ws = XLSX.utils.aoa_to_sheet(wsData);
        XLSX.utils.book_append_sheet(wb, ws, 'Sheet1');

        const safeName = data.employee_name.replace(/[\\/*?:"<>|]+/g, '_');
        const fileName = `${safeName}.xlsx`;
        XLSX.writeFile(wb, fileName);

        alert('✅ Все поля заполнены. Файл с данными скачан. Пожалуйста, отправьте его ответственному за сбор.');
    } catch (error) {
        console.error('Ошибка при сохранении файла:', error);
        alert('❌ Ошибка при сохранении файла. Пожалуйста, попробуйте ещё раз.');
    }
}

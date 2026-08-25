# main.py
import os
import sys
import glob
import json
import re
import shutil
import logging
from collections import defaultdict
from typing import Dict, Optional, List, Tuple

import pandas as pd
from jinja2 import Environment, FileSystemLoader, TemplateNotFound
import base64

from backend.parser import ExcelParser
from backend.merge import merge_reports
from backend.utils import normalize_person_name
from backend.config_validator import validate_config

# ---------- Настройка логирования ----------
LOG_FILE = os.getenv('LOG_FILE', 'logs/main.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ---------- Конфиг ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.environ.get('CONFIG_PATH', os.path.join(BASE_DIR, 'config.json'))
with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
    CONFIG = json.load(f)

# Валидация конфигурации
is_valid, errors = validate_config(CONFIG)
if not is_valid:
    logger.error("Конфигурация некорректна:")
    for error in errors:
        logger.error(f"  - {error}")
    sys.exit(1)
else:
    logger.info("Конфигурация успешно прошла валидацию")

AI_CONFIG = CONFIG['ai']
FILE_TYPES = CONFIG['file_types']

# ---------- Пути (из конфига или env) ----------
PATHS_CONFIG = CONFIG.get('paths', {})
TEMPLATES_DIR = os.getenv('TEMPLATES_DIR', os.path.join(BASE_DIR, PATHS_CONFIG.get('templates_dir', 'templates')))
STATIC_DIR = os.getenv('STATIC_DIR', os.path.join(BASE_DIR, PATHS_CONFIG.get('static_dir', 'static')))
VENDOR_DIR = os.path.join(STATIC_DIR, 'vendor')
STATIC_JS_DIR = os.path.join(STATIC_DIR, 'js')
DEFAULT_DATA_DIR = os.getenv('DATA_DIR', os.path.join(BASE_DIR, PATHS_CONFIG.get('data_dir', 'data')))
DEFAULT_OUTPUT_DIR = os.getenv('OUTPUT_DIR', os.path.join(BASE_DIR, PATHS_CONFIG.get('output_dir', 'output')))
LOGS_DIR = os.getenv('LOGS_DIR', os.path.join(BASE_DIR, PATHS_CONFIG.get('logs_dir', 'logs')))

# ---------- Вспомогательные функции ----------
def is_eval_file(file_path: str) -> bool:
    return 'eval' in os.path.basename(file_path).lower()


def get_employee_name_from_file(file_path: str) -> Optional[str]:
    try:
        with ExcelParser(file_path) as parser:
            meta = parser._extract_meta()
            name = meta.get('evaluated')
            return normalize_person_name(name) if name else None
    except Exception as e:
        logger.error(f"Не удалось прочитать файл {os.path.basename(file_path)}: {e}")
        return None


def group_files_by_employee(data_dir: str) -> Dict[str, Dict[str, str]]:
    files = glob.glob(os.path.join(data_dir, '*.xlsx'))
    if not files:
        logger.warning(f"В папке {data_dir} не найдено .xlsx файлов")
        return {}

    # Фильтруем временные и AI-файлы
    files = [f for f in files if not os.path.basename(f).startswith('~$') and not is_eval_file(f)]

    raw_groups = defaultdict(list)
    for f in files:
        name = get_employee_name_from_file(f)
        if name:
            raw_groups[name].append(f)
        else:
            logger.warning(f"Не удалось определить имя оцениваемого в файле: {os.path.basename(f)}")

    result = {}
    for emp_name, file_list in raw_groups.items():
        # Определяем обязательные типы файлов (исключаем subordinates, так как он опционален)
        required_types = [t for t in FILE_TYPES if t != 'subordinates']
        types_found = {t: None for t in FILE_TYPES}
        for f in file_list:
            try:
                with ExcelParser(f) as parser:
                    header_row = parser._find_row_with_text(1, CONFIG['parser']['competencies_section_text'])
                    if header_row:
                        atype = parser._detect_assessment_type(header_row)
                        if types_found[atype] is not None:
                            logger.warning(
                                f"Для сотрудника '{emp_name}' найдено несколько файлов типа '{atype}'. "
                                f"Используется: {os.path.basename(f)}"
                            )
                        types_found[atype] = f
                    else:
                        logger.warning(f"В файле {os.path.basename(f)} не найдена таблица компетенций")
            except Exception as e:
                logger.error(f"Ошибка при определении типа файла {os.path.basename(f)}: {e}")

        missing = [t for t in required_types if types_found.get(t) is None]
        if missing:
            logger.error(f"Для сотрудника '{emp_name}' отсутствуют обязательные файлы типов: {', '.join(missing)}. Пропускаем.")
            continue

        result[emp_name] = types_found

    return result


def load_ai_scores(data_dir: str) -> Dict[Tuple[str, str], Dict[str, str]]:
    files = sorted(glob.glob(os.path.join(data_dir, AI_CONFIG['file_pattern'])))
    if not files:
        logger.info("AI-файл не найден. Продолжаем без AI-оценок.")
        return {}

    if len(files) > 1:
        logger.warning(
            f"Найдено несколько AI-файлов, используется первый по алфавиту:\n"
            + "\n".join(f"   - {os.path.basename(f)}" for f in files)
        )

    ai_file = files[0]
    try:
        df = pd.read_excel(ai_file)
    except Exception as e:
        logger.error(f"Ошибка при чтении AI-файла {ai_file}: {e}")
        return {}

    cols = AI_CONFIG['columns']
    required_cols = [cols['employee_name'], cols['case_id'], cols['behavior_class'], cols['positive_patterns']]
    missing_cols = [col for col in required_cols if col not in df.columns]
    if missing_cols:
        logger.warning(f"В AI-файле отсутствуют колонки: {', '.join(missing_cols)}. Пропускаем AI-оценки.")
        return {}

    ai_dict = {}
    for _, row in df.iterrows():
        name = normalize_person_name(row[cols['employee_name']]).lower()
        case_id = str(row[cols['case_id']]).strip()
        behavior = str(row[cols['behavior_class']]).strip() if pd.notna(row[cols['behavior_class']]) else ''
        patterns = str(row[cols['positive_patterns']]).strip() if pd.notna(row[cols['positive_patterns']]) else ''
        ai_dict[(name, case_id)] = {'class': behavior, 'patterns': patterns}

    logger.info(f"Загружено {len(ai_dict)} AI-оценок из файла {os.path.basename(ai_file)}")
    return ai_dict


def get_logo_base64() -> Optional[str]:
    logo_path = os.path.join(STATIC_DIR, 'лого myteam черный.png')
    if os.path.exists(logo_path):
        try:
            with open(logo_path, 'rb') as f:
                encoded = base64.b64encode(f.read()).decode('utf-8')
            return f"data:image/png;base64,{encoded}"
        except Exception as e:
            logger.error(f"Ошибка чтения логотипа: {e}")
    else:
        logger.warning(f"Логотип не найден по пути: {logo_path}")
    return None


def copy_vendor_assets(output_dir: str, vendor_dir: str, static_js_dir: str) -> None:
    """
    Копирует vendor-файлы (chart.js, xlsx) и report.js в output директорию.
    Если файлы уже существуют и актуальны, копирование пропускается для оптимизации.
    """
    if not os.path.isdir(vendor_dir):
        raise FileNotFoundError(
            f"Папка с vendor-скриптами не найдена: {vendor_dir}. "
            "Убедитесь, что chart.js и xlsx лежат в static/vendor/."
        )
    
    if not os.path.isdir(static_js_dir):
        logger.warning(f"Папка со статическими JS файлами не найдена: {static_js_dir}")

    target_vendor_dir = os.path.join(output_dir, 'vendor')
    target_static_js_dir = os.path.join(output_dir, 'static', 'js')
    
    # Копируем vendor файлы
    if os.path.exists(target_vendor_dir):
        existing_files = os.listdir(target_vendor_dir)
        if existing_files:
            logger.debug(f"Vendor-файлы уже существуют в {target_vendor_dir}. Копирование пропущено.")
    else:
        os.makedirs(target_vendor_dir, exist_ok=True)
        for filename in os.listdir(vendor_dir):
            if filename.endswith('.js'):
                src = os.path.join(vendor_dir, filename)
                dst = os.path.join(target_vendor_dir, filename)
                shutil.copy2(src, dst)
                logger.debug(f"Скопирован {filename} -> {dst}")
    
    # Копируем report.js
    if os.path.isdir(static_js_dir):
        report_js_src = os.path.join(static_js_dir, 'report.js')
        if os.path.exists(report_js_src):
            os.makedirs(target_static_js_dir, exist_ok=True)
            report_js_dst = os.path.join(target_static_js_dir, 'report.js')
            # Всегда копируем report.js, чтобы убедиться в актуальности
            shutil.copy2(report_js_src, report_js_dst)
            logger.debug(f"Скопирован report.js -> {report_js_dst}")
        else:
            logger.warning(f"Файл report.js не найден в {static_js_dir}")
    else:
        logger.warning(f"Папка static/js не найдена: {static_js_dir}")


def generate_html(report: Dict, output_dir: str, vendor_dir: str, static_js_dir: str) -> str:
    if not os.path.exists(TEMPLATES_DIR):
        raise FileNotFoundError(f"Папка 'templates' не найдена: {TEMPLATES_DIR}")

    # Создаем Jinja2 environment и регистрируем фильтр escapejs
    env = Environment(loader=FileSystemLoader(TEMPLATES_DIR))
    
    # Добавляем кастомный фильтр escapejs
    def escapejs_filter(value):
        """Экранирует специальные символы для использования в JavaScript"""
        if not isinstance(value, str):
            value = str(value) if value is not None else ''
        value = value.replace('\\', '\\\\')
        value = value.replace("'", "\\'")
        value = value.replace('"', '\\"')
        value = value.replace('\n', '\\n')
        value = value.replace('\r', '\\r')
        value = value.replace('</', '<\\/')
        return value
    
    env.filters['escapejs'] = escapejs_filter
    
    try:
        template = env.get_template('report.html')
    except TemplateNotFound:
        raise FileNotFoundError(f"Шаблон report.html не найден в {TEMPLATES_DIR}")

    logo_base64 = get_logo_base64()

    html_content = template.render(
        employee=report['employee'],
        manager=report['manager'],
        colleagues=report['colleagues'],
        soft_skills=report['soft_skills'],
        soft_blocks=report['soft_blocks'],
        managerial_block=report.get('managerial_block', {}),
        managerial_skills=report.get('managerial_skills', {'labels': [], 'self': [], 'manager': [], 'colleagues': [], 'subordinates': []}),
        cases=report['cases'],
        performance=report['performance'],
        all_competencies=sorted(set(report['soft_skills']['labels']) | set(report.get('managerial_skills', {}).get('labels', []))),
        logo_base64=logo_base64,
        soft_recommendations=report.get('soft_recommendations', {}),
        behavioral_patterns=report.get('behavioral_patterns', [])
    )

    copy_vendor_assets(output_dir, vendor_dir, static_js_dir)

    out_path = os.path.join(output_dir, 'report.html')
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(html_content)

    return out_path


def process_employee(emp_name: str, files_dict: Dict[str, str], ai_scores: Dict, output_base: str) -> bool:
    logger.info(f"Обработка сотрудника: {emp_name}")

    try:
        with ExcelParser(files_dict['self']) as parser_self:
            data_self = parser_self.parse()
        with ExcelParser(files_dict['manager']) as parser_manager:
            data_manager = parser_manager.parse()
        with ExcelParser(files_dict['colleagues']) as parser_colleagues:
            data_colleagues = parser_colleagues.parse()
        
        # Подчиненные - опционально
        data_subordinates = None
        if 'subordinates' in files_dict and files_dict['subordinates']:
            try:
                with ExcelParser(files_dict['subordinates']) as parser_subordinates:
                    data_subordinates = parser_subordinates.parse()
            except Exception as e:
                logger.warning(f"Не удалось прочитать файл подчиненных для {emp_name}: {e}")
    except Exception as e:
        logger.error(f"Ошибка парсинга файлов для {emp_name}: {e}")
        return False

    try:
        report = merge_reports(data_self, data_manager, data_colleagues, ai_scores=ai_scores, subordinates_data=data_subordinates)
    except Exception as e:
        logger.error(f"Ошибка при объединении данных для {emp_name}: {e}")
        return False

    safe_name = re.sub(r'[\\/*?:"<>|]', '_', emp_name)
    out_dir = os.path.join(output_base, safe_name)
    os.makedirs(out_dir, exist_ok=True)

    # JSON
    json_path = os.path.join(out_dir, 'report_data.json')
    try:
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        logger.info(f"JSON сохранён: {json_path}")
    except Exception as e:
        logger.error(f"Ошибка сохранения JSON для {emp_name}: {e}")

    # HTML
    try:
        html_path = generate_html(report, out_dir, VENDOR_DIR, STATIC_JS_DIR)
        logger.info(f"HTML сохранён: {html_path}")
    except Exception as e:
        logger.error(f"Ошибка генерации HTML для {emp_name}: {e}")
        return False

    logger.info(f"Для {emp_name}: Soft={len(report['soft_skills']['labels'])}, Managerial={len(report.get('managerial_skills', {}).get('labels', []))}, Кейсов={len(report['cases'])}")
    return True


def main(data_dir: Optional[str] = None, output_dir: Optional[str] = None) -> None:
    data_dir = data_dir or DEFAULT_DATA_DIR
    output_dir = output_dir or DEFAULT_OUTPUT_DIR

    if not os.path.isabs(data_dir):
        data_dir = os.path.join(BASE_DIR, data_dir)
    if not os.path.isabs(output_dir):
        output_dir = os.path.join(BASE_DIR, output_dir)

    if not os.path.exists(data_dir):
        logger.error(f"Папка с данными не найдена: {data_dir}")
        sys.exit(1)

    if not os.path.exists(TEMPLATES_DIR):
        logger.error(f"Папка с шаблонами не найдена: {TEMPLATES_DIR}")
        sys.exit(1)
    if not os.path.isdir(VENDOR_DIR):
        logger.error(f"Папка vendor не найдена: {VENDOR_DIR}. Убедитесь, что chart.js и xlsx лежат в static/vendor/.")
        sys.exit(1)

    ai_scores = load_ai_scores(data_dir)

    groups = group_files_by_employee(data_dir)
    if not groups:
        logger.warning("Не найдено ни одной полной группы файлов для сотрудников.")
        return

    logger.info(f"Найдено {len(groups)} сотрудников:")
    for emp in groups:
        logger.info(f"   - {emp}")

    success_count = 0
    for emp_name, files in groups.items():
        ok = process_employee(emp_name, files, ai_scores, output_dir)
        if ok:
            success_count += 1

    logger.info(f"\n🎉 Обработка завершена. Успешно: {success_count} из {len(groups)}.")
    if success_count < len(groups):
        logger.warning("Некоторые сотрудники не были обработаны. Проверьте логи выше.")


if __name__ == '__main__':
    if len(sys.argv) > 1:
        main(sys.argv[1])
    else:
        main()
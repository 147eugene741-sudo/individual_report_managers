# backend/parser.py
import openpyxl
import json
import os
import logging
from typing import Dict, List, Optional, Tuple
from openpyxl.utils.exceptions import InvalidFileException
from openpyxl.worksheet.worksheet import Worksheet

logger = logging.getLogger(__name__)

# Путь к корню проекта (на уровень выше backend)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get('CONFIG_PATH', os.path.join(BASE_DIR, 'config.json'))

try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    logger.error(f"Файл конфигурации не найден: {CONFIG_PATH}")
    raise
except json.JSONDecodeError as e:
    logger.error(f"Ошибка JSON в файле конфигурации {CONFIG_PATH}: {e}")
    raise

PARSER_CONFIG = CONFIG['parser']
AI_CONFIG = CONFIG['ai']
SOFT_BLOCK_MAP = CONFIG.get('soft_block_map', {})

# Магические числа вынесены в конфиг или константы
MAX_INSTRUCTION_LENGTH = PARSER_CONFIG.get('max_instruction_length', 80)
MIN_COMPETENCY_NAME_LENGTH = PARSER_CONFIG.get('min_competency_name_length', 3)

# Управленческие компетенции (фиксированный список)
MANAGERIAL_COMPETENCIES = [
    "Формирование и построение команды",
    "Каскадирование стратегии",
    "Управление эффективностью команды",
    "Управление ресурсами и бюджетом",
    "Представление и защита интересов команды"
]

# Префиксы для маппинга управленческих компетенций
MANAGERIAL_PREFIXES = ["РУК ", "РУК.", "РУК:"]


def _normalize_competency_name(name: str) -> str:
    """Нормализует название компетенции, удаляя префиксы типа 'РУК '."""
    name = name.strip()
    for prefix in MANAGERIAL_PREFIXES:
        if name.startswith(prefix):
            return name[len(prefix):].strip()
    return name


def _is_managerial_competency(name: str) -> bool:
    """Проверяет, является ли компетенция управленческой (с учетом префиксов)."""
    normalized = _normalize_competency_name(name)
    return normalized in MANAGERIAL_COMPETENCIES


def _get_managerial_competency_name(name: str) -> str:
    """Возвращает нормализованное название управленческой компетенции."""
    normalized = _normalize_competency_name(name)
    return normalized if normalized in MANAGERIAL_COMPETENCIES else name


class ExcelParser:
    def __init__(self, file_path: str):
        self.file_path = file_path
        try:
            self.wb = openpyxl.load_workbook(file_path, data_only=True)
            self.sheet: Worksheet = self.wb.active
        except FileNotFoundError:
            logger.error(f"Файл не найден: {file_path}")
            raise
        except InvalidFileException as e:
            logger.error(f"Некорректный формат Excel файла {file_path}: {e}")
            raise
        except Exception as e:
            logger.error(f"Ошибка при открытии файла {file_path}: {e}")
            raise
        self.assessment_type = None

    def close(self):
        if self.wb is not None:
            try:
                self.wb.close()
            except Exception as e:
                logger.warning(f"Ошибка при закрытии workbook: {e}")
            finally:
                self.wb = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def _find_row_with_text(self, start_row: int, text: str, col: int = 1) -> Optional[int]:
        """Ищет строку, содержащую указанный текст."""
        try:
            for row in range(start_row, self.sheet.max_row + 1):
                cell_value = self.sheet.cell(row=row, column=col).value
                if cell_value and text in str(cell_value):
                    return row
        except Exception as e:
            logger.warning(f"Ошибка при поиске строки с текстом '{text}': {e}")
        return None

    def _get_column_index(self, header_row: int, header_text: str) -> Optional[int]:
        """Возвращает индекс колонки по тексту заголовка."""
        try:
            for col in range(1, self.sheet.max_column + 1):
                val = self.sheet.cell(row=header_row, column=col).value
                if val and header_text in str(val):
                    return col
        except Exception as e:
            logger.warning(f"Ошибка при поиске колонки '{header_text}': {e}")
        return None

    @staticmethod
    def _normalize_score(value) -> Optional[int]:
        """Приводит оценку к целому числу от 1 до 4, игнорируя 5 и None."""
        if value is None or value == 5:
            return None
        try:
            score = int(value)
        except (TypeError, ValueError):
            return None
        if 1 <= score <= 4:
            return score
        return None

    def _extract_meta(self) -> Dict:
        """Извлекает метаданные (ID, ФИО, дата, имя опроса)."""
        meta = {}
        try:
            for row in range(1, 11):
                cell_a = self.sheet.cell(row=row, column=1).value
                if not cell_a:
                    continue
                cell_label = str(cell_a)
                cell_value = self.sheet.cell(row=row, column=2).value
                if PARSER_CONFIG['meta_id_label'] in cell_label:
                    meta['survey_id'] = str(cell_value).strip() if cell_value is not None else ''
                elif PARSER_CONFIG['meta_evaluated_label'] in cell_label:
                    meta['evaluated'] = str(cell_value).strip() if cell_value is not None else ''
                elif PARSER_CONFIG['meta_date_label'] in cell_label:
                    meta['date'] = str(cell_value).strip() if cell_value is not None else ''
                elif PARSER_CONFIG['meta_survey_name_label'] in cell_label:
                    meta['survey_name'] = str(cell_value).strip() if cell_value is not None else ''
        except Exception as e:
            logger.warning(f"Ошибка при извлечении метаданных: {e}")
        return meta

    def _detect_assessment_type(self, header_row: int) -> str:
        """
        Определяет тип опроса (self, manager, colleagues, subordinates) по наличию оценок в колонках.
        """
        col_map = {}
        for col_name in [PARSER_CONFIG['self_column_label'],
                         PARSER_CONFIG['manager_column_label'],
                         PARSER_CONFIG['colleagues_column_label'],
                         PARSER_CONFIG.get('subordinates_column_label')]:
            if col_name:  # Проверяем, что ключ существует
                col_idx = self._get_column_index(header_row, col_name)
                if col_idx:
                    col_map[col_name] = col_idx

        scores_found = {col_name: False for col_name in col_map}
        for row in range(header_row + 1, min(header_row + 30, self.sheet.max_row + 1)):
            comp_name = self.sheet.cell(row=row, column=1).value
            if not comp_name:
                continue
            comp_lower = str(comp_name).lower()
            if any(key in comp_lower for key in PARSER_CONFIG['exclude_keywords']):
                continue
            if PARSER_CONFIG['color_explanation_text'].lower() in comp_lower:
                break

            for col_name, col_idx in col_map.items():
                val = self.sheet.cell(row=row, column=col_idx).value
                if self._normalize_score(val) is not None:
                    scores_found[col_name] = True

        if scores_found.get(PARSER_CONFIG['self_column_label']):
            return 'self'
        if scores_found.get(PARSER_CONFIG['manager_column_label']):
            return 'manager'
        if scores_found.get(PARSER_CONFIG['colleagues_column_label']):
            return 'colleagues'
        if PARSER_CONFIG.get('subordinates_column_label') and scores_found.get(PARSER_CONFIG['subordinates_column_label']):
            return 'subordinates'

        # fallback по имени опроса
        meta = self._extract_meta()
        survey_name = meta.get('survey_name', '').lower()
        if 'самооценка' in survey_name:
            return 'self'
        if 'руководитель' in survey_name:
            return 'manager'
        if 'коллег' in survey_name:
            return 'colleagues'
        if 'подчиненн' in survey_name:
            return 'subordinates'
        raise ValueError("Не удалось определить тип опроса")

    def _parse_competencies(self) -> Tuple[List[Tuple[str, int]], List[Tuple[str, int]]]:
        """
        Парсит таблицу компетенций и возвращает (soft_comp, hard_comp) в виде списков (название, оценка).
        """
        header_row = self._find_row_with_text(1, PARSER_CONFIG['competencies_section_text'])
        if not header_row:
            return [], []

        if not self.assessment_type:
            self.assessment_type = self._detect_assessment_type(header_row)

        # Определяем, какую колонку читать
        type_to_label = {
            'self': PARSER_CONFIG['self_column_label'],
            'manager': PARSER_CONFIG['manager_column_label'],
            'colleagues': PARSER_CONFIG['colleagues_column_label'],
            'subordinates': PARSER_CONFIG.get('subordinates_column_label')
        }
        col_name = type_to_label.get(self.assessment_type)
        if not col_name:
            raise ValueError(f"Неизвестный тип оценки: {self.assessment_type}")
        col_idx = self._get_column_index(header_row, col_name)
        if not col_idx:
            raise ValueError(f"Не найдена колонка '{col_name}'")

        def is_instruction(text: str) -> bool:
            text_lower = text.lower()
            for phrase in PARSER_CONFIG['stop_phrases_for_instruction']:
                if phrase in text_lower:
                    return True
            return len(text) > MAX_INSTRUCTION_LENGTH  # если слишком длинный, считаем инструкцией

        soft_comp = []
        managerial_comp = []
        current_section = None
        found_soft_instruction = False
        hard_section_found = False

        for row in range(header_row + 1, self.sheet.max_row + 1):
            cell_value = self.sheet.cell(row=row, column=1).value
            if not cell_value:
                continue
            cell_str = str(cell_value).strip()

            if PARSER_CONFIG['soft_instruction_text'].lower() in cell_str.lower():
                current_section = 'soft'
                found_soft_instruction = True
                continue
            
            # Пропускаем строку с инструкцией для хардов (если есть)
            if PARSER_CONFIG['hard_instruction_text'].lower() in cell_str.lower():
                hard_section_found = True
                continue

            if current_section is None:
                continue

            # Пропускаем строки с ключевыми словами
            if any(key in cell_str.lower() for key in PARSER_CONFIG['exclude_keywords']):
                continue

            # Пропускаем строки с ' - ' или начинающиеся с 'Сотрудник'
            if ' - ' in cell_str or cell_str.startswith('Сотрудник'):
                continue

            # Пропускаем слишком короткие названия компетенций
            if len(cell_str) < MIN_COMPETENCY_NAME_LENGTH:
                continue

            if is_instruction(cell_str):
                continue

            if PARSER_CONFIG['color_explanation_text'].lower() in cell_str.lower():
                break

            score = self._normalize_score(self.sheet.cell(row=row, column=col_idx).value)
            if score is not None:
                # Проверяем, является ли компетенция управленческой (даже если она в блоке soft)
                if _is_managerial_competency(cell_str):
                    normalized_name = _get_managerial_competency_name(cell_str)
                    managerial_comp.append((normalized_name, score))
                elif current_section == 'soft':
                    soft_comp.append((cell_str, score))

        return soft_comp, managerial_comp

    def _parse_open_questions(self) -> List[Dict]:
        """Парсит блок открытых вопросов."""
        start_row = self._find_row_with_text(1, PARSER_CONFIG['open_questions_section_text'])
        if not start_row:
            return []

        # Определяем колонку для ответов
        type_to_label = {
            'self': PARSER_CONFIG['self_column_label'],
            'manager': PARSER_CONFIG['manager_column_label'],
            'colleagues': PARSER_CONFIG['colleagues_column_label'],
            'subordinates': PARSER_CONFIG.get('subordinates_column_label')
        }
        col_name = type_to_label.get(self.assessment_type)
        if not col_name:
            answer_col = 2  # fallback
        else:
            answer_col = self._get_column_index(start_row, col_name)
            if not answer_col:
                answer_col = 2  # fallback

        questions = []
        for row in range(start_row + 1, self.sheet.max_row + 1):
            q_cell = self.sheet.cell(row=row, column=1).value
            if not q_cell:
                continue
            q_str = str(q_cell).strip()
            if PARSER_CONFIG['question_prefix'] in q_str or PARSER_CONFIG['case_title_marker'] in q_str:
                answer = self.sheet.cell(row=row, column=answer_col).value
                if not answer or str(answer).strip() == '':
                    # Проверяем следующую строку (иногда ответ переносится)
                    next_row = row + 1
                    if next_row <= self.sheet.max_row:
                        next_answer = self.sheet.cell(row=next_row, column=answer_col).value
                        if next_answer and str(next_answer).strip() != '':
                            answer = next_answer
                if answer:
                    questions.append({
                        'question': q_str,
                        'answer': str(answer).strip()
                    })
        return questions

    def parse(self) -> Dict:
        """Основной метод парсинга."""
        meta = self._extract_meta()
        soft_comps, managerial_comps = self._parse_competencies()
        open_qs = self._parse_open_questions()

        return {
            'meta': meta,
            'competencies': {
                'soft': {
                    'labels': [c[0] for c in soft_comps],
                    'scores': [c[1] for c in soft_comps]
                },
                'managerial': {
                    'labels': [c[0] for c in managerial_comps],
                    'scores': [c[1] for c in managerial_comps]
                }
            },
            'open_questions': open_qs
        }
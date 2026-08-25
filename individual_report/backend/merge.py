# backend/merge.py
import re
import logging
import json
import os
from collections import defaultdict
from typing import Dict, List, Any, Optional

from .utils import normalize_competency_name, normalize_person_name, normalize_person_key

logger = logging.getLogger(__name__)

# Путь к корню проекта
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.environ.get('CONFIG_PATH', os.path.join(BASE_DIR, 'config.json'))

try:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        CONFIG = json.load(f)
except FileNotFoundError:
    logger.error(f"Файл конфигурации не найден: {CONFIG_PATH}")
    raise

SOFT_BLOCK_MAP = CONFIG['soft_block_map']
COMPETENCY_DESCRIPTIONS = CONFIG.get('competency_descriptions', {})
CASE_ID_REGEX = CONFIG['case_id_regex']
RECOMMENDATION_SCENARIOS = CONFIG.get('recommendation_scenarios', {})
BEHAVIORAL_PATTERNS = CONFIG.get('behavioral_patterns', {})


def _safe_get(data: Dict, keys: List[str], default=None) -> Any:
    for key in keys:
        if not isinstance(data, dict):
            return default
        data = data.get(key, default)
        if data is None:
            return default
    return data


def _extract_competencies(data: Dict, comp_type: str, source: str) -> Dict[str, Optional[float]]:
    result = {}
    comp_data = _safe_get(data, ['competencies', comp_type], {})
    labels = comp_data.get('labels', [])
    scores = comp_data.get('scores', [])

    if not labels or not scores:
        logger.warning(f"Нет данных по {comp_type} для источника {source}")
        return result

    if len(labels) != len(scores):
        logger.error(f"Несоответствие длины labels и scores для {comp_type} в {source}")
        return result

    for label, score in zip(labels, scores):
        # Проверка типа данных перед нормализацией
        if not isinstance(label, str):
            logger.warning(f"Некорректный тип названия компетенции: {type(label)}. Пропускаем.")
            continue
        norm = normalize_competency_name(label)
        if norm:
            result[norm] = score
    return result


def _build_soft_blocks(all_soft_keys: set, self_soft: dict, manager_soft: dict, colleagues_soft: dict, subordinates_soft: dict = None) -> List[Dict]:
    if subordinates_soft is None:
        subordinates_soft = {}
    
    block_data = defaultdict(list)
    for comp in all_soft_keys:
        block_name = SOFT_BLOCK_MAP.get(comp)
        if block_name:
            block_data[block_name].append(comp)

    soft_blocks = []
    for block_name, comps in block_data.items():
        block_self = []
        block_mgr = []
        block_col = []
        block_sub = []

        for comp in comps:
            if comp in self_soft and self_soft[comp] is not None:
                block_self.append(self_soft[comp])
            if comp in manager_soft and manager_soft[comp] is not None:
                block_mgr.append(manager_soft[comp])
            if comp in colleagues_soft and colleagues_soft[comp] is not None:
                block_col.append(colleagues_soft[comp])
            if comp in subordinates_soft and subordinates_soft[comp] is not None:
                block_sub.append(subordinates_soft[comp])

        avg_self = round(sum(block_self) / len(block_self), 2) if block_self else None
        avg_mgr = round(sum(block_mgr) / len(block_mgr), 2) if block_mgr else None
        avg_col = round(sum(block_col) / len(block_col), 2) if block_col else None
        avg_sub = round(sum(block_sub) / len(block_sub), 2) if block_sub else None

        # Получаем описания для блока и компетенций
        block_desc = COMPETENCY_DESCRIPTIONS.get('blocks', {}).get(block_name, '')
        comp_descriptions = COMPETENCY_DESCRIPTIONS.get('competencies', {})
        
        # Формируем описания для каждой компетенции в блоке
        comp_desc_map = {}
        for comp in comps:
            # Приводим название компетенции к формату с заглавной буквы для поиска в маппинге
            comp_title = comp.capitalize()
            comp_desc_map[comp] = comp_descriptions.get(comp_title, '')

        soft_blocks.append({
            'name': block_name,
            'description': block_desc,
            'competencies': comps,
            'competency_descriptions': comp_desc_map,
            'averages': {
                'self': avg_self,
                'manager': avg_mgr,
                'colleagues': avg_col,
                'subordinates': avg_sub
            }
        })

    return soft_blocks


def _extract_cases(self_data: Dict, employee_key: str, ai_scores: Dict) -> List[Dict]:
    """
    Извлекает только те открытые вопросы, которые являются кейсами.
    Кейс определяется наличием маркера '|Case_Title >>' или ID в формате, заданном CASE_ID_REGEX.
    """
    cases = []
    open_questions = _safe_get(self_data, ['open_questions'], [])

    for item in open_questions:
        question = item.get('question', '')
        answer = item.get('answer', '')

        # Проверяем, является ли вопрос кейсом
        # 1) Содержит маркер Case_Title
        # 2) Или соответствует регулярному выражению для ID кейса
        has_case_title = '|Case_Title >>' in question
        match_id = re.search(CASE_ID_REGEX, question)
        if not has_case_title and not match_id:
            continue  # не кейс – пропускаем

        # Извлекаем ID кейса (если есть)
        case_id = match_id.group(1) if match_id else ''

        # Извлекаем заголовок (если есть)
        title = ''
        if has_case_title:
            parts = question.split('|Case_Title >>')
            if len(parts) > 1:
                title = parts[1].strip()

        # AI-информация
        ai_info = ai_scores.get((employee_key, case_id), {}) if ai_scores else {}
        ai_score = ai_info.get('class', '')
        positive_patterns = ai_info.get('patterns', '')

        cases.append({
            'id': case_id,
            'title': title,
            'question': question,
            'answer': answer,
            'manager_comment': '',
            'level': '',
            'ai_score': ai_score,
            'positive_patterns': positive_patterns
        })

    return cases


def _get_soft_skills_recommendation(avg_score: Optional[float], assessment_type: str) -> str:
    """
    Возвращает текстовый вывод (сценарий) на основе средней оценки по soft-компетенциям.
    
    :param avg_score: Средняя оценка (от 1 до 4) или None, если данных нет
    :param assessment_type: Тип оценки ('self', 'colleagues', 'manager', 'subordinates')
    :return: Текстовый вывод согласно таблице сценариев из конфига
    """
    if avg_score is None:
        return "Нет данных для формирования вывода."
    
    # Получаем сценарии из конфига
    scenario_list = RECOMMENDATION_SCENARIOS.get(assessment_type, [])
    
    if not scenario_list:
        logger.warning(f"Сценарии для типа '{assessment_type}' не найдены в конфиге")
        return "Нет данных для формирования вывода."
    
    for min_score, max_score, text in scenario_list:
        if min_score <= avg_score <= max_score:
            return text
    
    # Если оценка вышла за пределы
    if avg_score > 4.0 and scenario_list:
        return scenario_list[-1][2]
    elif avg_score < 1.0 and scenario_list:
        return scenario_list[0][2]
    
    return "Нет данных для формирования вывода."


def _get_behavioral_patterns(manager_soft: Dict[str, Optional[float]], manager_avg: Optional[float]) -> List[Dict[str, str]]:
    """
    Возвращает список поведенческих паттернов на основе оценок руководителя по каждой компетенции.
    
    :param manager_soft: Словарь с оценками руководителя по soft-компетенциям
    :param manager_avg: Средняя оценка руководителя по всем soft-компетенциям
    :return: Список словарей с названием блока и текстом сценария из конфига
    """
    if manager_avg is None:
        return []
    
    # Создаем обратный маппинг: блок -> список компетенций
    block_to_comps = {}
    for comp, block in SOFT_BLOCK_MAP.items():
        if block not in block_to_comps:
            block_to_comps[block] = []
        block_to_comps[block].append(comp)
    
    patterns = []
    
    # Для каждого блока компетенций рассчитываем среднюю оценку и подбираем сценарий
    for block_name, comp_list in block_to_comps.items():
        # Получаем оценки менеджера для компетенций этого блока
        block_scores = []
        for comp in comp_list:
            if comp in manager_soft and manager_soft[comp] is not None:
                block_scores.append(manager_soft[comp])
        
        if block_scores:
            block_avg = sum(block_scores) / len(block_scores)
            
            # Находим подходящий сценарий для этого блока из конфига
            scenario_list = BEHAVIORAL_PATTERNS.get(block_name, [])
            scenario_text = None
            
            if not scenario_list:
                logger.warning(f"Поведенческие паттерны для блока '{block_name}' не найдены в конфиге")
                continue
            
            for min_score, max_score, text in scenario_list:
                if min_score <= block_avg <= max_score:
                    scenario_text = text
                    break
            
            # Если оценка вышла за пределы
            if scenario_text is None:
                if block_avg > 4.0 and scenario_list:
                    scenario_text = scenario_list[-1][2]
                elif block_avg < 1.0 and scenario_list:
                    scenario_text = scenario_list[0][2]
            
            if scenario_text:
                patterns.append({
                    'block_name': block_name,
                    'scenario': scenario_text
                })
    
    return patterns


def merge_reports(self_data: Dict, manager_data: Dict, colleagues_data: Dict, ai_scores: Optional[Dict] = None, subordinates_data: Optional[Dict] = None) -> Dict:
    if ai_scores is None:
        ai_scores = {}

    self_meta = _safe_get(self_data, ['meta'], {})
    manager_meta = _safe_get(manager_data, ['meta'], {})
    colleagues_meta = _safe_get(colleagues_data, ['meta'], {})
    subordinates_meta = _safe_get(subordinates_data, ['meta'], {}) if subordinates_data else {}

    employee = {
        'name': normalize_person_name(self_meta.get('evaluated', '')),
        'id': str(self_meta.get('survey_id', '')).strip(),
        'date': self_meta.get('date', '')
    }

    manager = {
        'survey_id': str(manager_meta.get('survey_id', '')).strip(),
    }

    colleagues = {
        'survey_id': str(colleagues_meta.get('survey_id', '')).strip(),
    }

    # Soft
    self_soft = _extract_competencies(self_data, 'soft', 'self')
    manager_soft = _extract_competencies(manager_data, 'soft', 'manager')
    colleagues_soft = _extract_competencies(colleagues_data, 'soft', 'colleagues')
    subordinates_soft = _extract_competencies(subordinates_data, 'soft', 'subordinates') if subordinates_data else {}

    all_soft_keys = set(self_soft.keys()) | set(manager_soft.keys()) | set(colleagues_soft.keys()) | set(subordinates_soft.keys())
    sorted_soft_keys = sorted(all_soft_keys)

    soft_labels = []
    self_scores = []
    manager_scores = []
    colleagues_scores = []
    subordinates_scores = []
    for key in sorted_soft_keys:
        soft_labels.append(key)
        self_scores.append(self_soft.get(key))
        manager_scores.append(manager_soft.get(key))
        colleagues_scores.append(colleagues_soft.get(key))
        subordinates_scores.append(subordinates_soft.get(key))

    soft_blocks = _build_soft_blocks(all_soft_keys, self_soft, manager_soft, colleagues_soft, subordinates_soft)

    # Hard
    self_hard = _extract_competencies(self_data, 'hard', 'self')
    manager_hard = _extract_competencies(manager_data, 'hard', 'manager')

    all_hard_keys = set(self_hard.keys()) | set(manager_hard.keys())
    sorted_hard_keys = sorted(all_hard_keys)

    hard_labels = []
    self_hard_scores = []
    manager_hard_scores = []
    for key in sorted_hard_keys:
        hard_labels.append(key)
        self_hard_scores.append(self_hard.get(key))
        manager_hard_scores.append(manager_hard.get(key))

    # Cases
    employee_key = normalize_person_key(employee.get('name', ''))
    cases = _extract_cases(self_data, employee_key, ai_scores)

    # Manager open answers
    manager_open_questions = _safe_get(manager_data, ['open_questions'], [])
    manager_open_answers = [item.get('answer', '') for item in manager_open_questions if item.get('answer')]

    # Рассчитываем средние оценки по soft skills для каждого источника
    # Фильтруем None значения перед суммированием
    self_scores_filtered = [s for s in self_scores if s is not None]
    manager_scores_filtered = [s for s in manager_scores if s is not None]
    colleagues_scores_filtered = [s for s in colleagues_scores if s is not None]
    subordinates_scores_filtered = [s for s in subordinates_scores if s is not None]
    
    self_avg = round(sum(self_scores_filtered) / len(self_scores_filtered), 3) if self_scores_filtered else None
    manager_avg = round(sum(manager_scores_filtered) / len(manager_scores_filtered), 3) if manager_scores_filtered else None
    colleagues_avg = round(sum(colleagues_scores_filtered) / len(colleagues_scores_filtered), 3) if colleagues_scores_filtered else None
    subordinates_avg = round(sum(subordinates_scores_filtered) / len(subordinates_scores_filtered), 3) if subordinates_scores_filtered else None
    
    # Генерируем выводы (рекомендации) на основе средних оценок
    soft_recommendations = {
        'self': _get_soft_skills_recommendation(self_avg, 'self'),
        'colleagues': _get_soft_skills_recommendation(colleagues_avg, 'colleagues'),
        'manager': _get_soft_skills_recommendation(manager_avg, 'manager'),
        'subordinates': _get_soft_skills_recommendation(subordinates_avg, 'subordinates') if subordinates_avg else None
    }
    
    # Генерируем поведенческие паттерны на основе оценок руководителя
    behavioral_patterns = _get_behavioral_patterns(manager_soft, manager_avg)

    performance = {
        'current_goals': '',
        'current_task': '',
        'current_task_score': None,
        'goal_future': '',
        'future_task': '',
        'related_competencies': [],
        'final_grade': '',
        'final_justification': '',
        'perform_rating': '',
        'strengths': '',
        'weaknesses': '',
        'goals_current': '',
        'ai_grade': '',
        'manager_grade': '',
        'task_score': ''
    }

    logger.info(f"Обработан сотрудник {employee['name']} (ID: {employee['id']})")
    logger.debug(f"Soft: {len(soft_labels)}, Hard: {len(hard_labels)}, Кейсов: {len(cases)}")

    return {
        'employee': employee,
        'manager': manager,
        'colleagues': colleagues,
        'soft_skills': {
            'labels': soft_labels,
            'self': self_scores,
            'manager': manager_scores,
            'colleagues': colleagues_scores,
            'subordinates': subordinates_scores,
            'managerDetails': manager_soft  # Используем словарь менеджера для деталей
        },
        'soft_blocks': soft_blocks,
        'hard_skills': {
            'labels': hard_labels,
            'self': self_hard_scores,
            'manager': manager_hard_scores
        },
        'cases': cases,
        'manager_open_answers': manager_open_answers,
        'performance': performance,
        'soft_recommendations': soft_recommendations,
        'behavioral_patterns': behavioral_patterns
    }
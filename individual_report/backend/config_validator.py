# backend/config_validator.py
import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


def validate_config(config: Dict) -> Tuple[bool, List[str]]:
    """
    Валидирует конфигурационный файл.
    
    :param config: Словарь с конфигурацией
    :return: Кортеж (is_valid, list_of_errors)
    """
    errors = []
    
    # Проверка на дубликаты компетенций в soft_block_map
    soft_block_map = config.get('soft_block_map', {})
    if soft_block_map:
        competency_names = list(soft_block_map.keys())
        normalized_names = [name.lower().strip() for name in competency_names]
        
        seen = set()
        duplicates = []
        for i, name in enumerate(normalized_names):
            if name in seen:
                duplicates.append(competency_names[i])
            seen.add(name)
        
        if duplicates:
            errors.append(f"Обнаружены дубликаты компетенций в soft_block_map: {', '.join(duplicates)}")
    
    # Проверка на пустые названия блоков
    for comp, block in soft_block_map.items():
        if not comp or not comp.strip():
            errors.append("Обнаружена компетенция с пустым названием в soft_block_map")
        if not block or not block.strip():
            errors.append(f"Компетенция '{comp}' имеет пустое название блока")
    
    # Проверка parser config
    parser_config = config.get('parser', {})
    required_parser_keys = [
        'competencies_section_text',
        'soft_instruction_text',
        'hard_instruction_text',
        'open_questions_section_text'
    ]
    for key in required_parser_keys:
        if key not in parser_config:
            errors.append(f"В секции 'parser' отсутствует обязательный ключ: {key}")
    
    # Проверка ai config
    ai_config = config.get('ai', {})
    required_ai_columns = ['employee_name', 'case_id', 'behavior_class', 'positive_patterns']
    ai_columns = ai_config.get('columns', {})
    for col in required_ai_columns:
        if col not in ai_columns:
            errors.append(f"В секции 'ai.columns' отсутствует обязательная колонка: {col}")
    
    # Проверка recommendation_scenarios
    recommendation_scenarios = config.get('recommendation_scenarios', {})
    required_scenario_types = ['self', 'colleagues', 'manager', 'subordinates']
    for scenario_type in required_scenario_types:
        if scenario_type not in recommendation_scenarios:
            logger.warning(f"В конфиге отсутствуют сценарии для типа '{scenario_type}'. Будут использоваться значения по умолчанию.")
        else:
            scenarios = recommendation_scenarios[scenario_type]
            if not isinstance(scenarios, list) or len(scenarios) == 0:
                errors.append(f"Сценарии для '{scenario_type}' должны быть непустым списком")
    
    # Проверка behavioral_patterns
    behavioral_patterns = config.get('behavioral_patterns', {})
    expected_blocks = set(soft_block_map.values())
    for block_name in expected_blocks:
        if block_name not in behavioral_patterns:
            logger.warning(f"В конфиге отсутствуют поведенческие паттерны для блока '{block_name}'")
        else:
            patterns = behavioral_patterns[block_name]
            if not isinstance(patterns, list) or len(patterns) == 0:
                errors.append(f"Поведенческие паттерны для '{block_name}' должны быть непустым списком")
    
    is_valid = len(errors) == 0
    return is_valid, errors

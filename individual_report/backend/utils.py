# utils.py
import re
from typing import Optional

def normalize_competency_name(name: Optional[str]) -> str:
    """
    Нормализует название компетенции: приводит к нижнему регистру,
    обрезает пробелы, удаляет суффиксы после '>>', убирает пунктуацию в конце.
    """
    if not name:
        return ""
    s = str(name).strip().lower()
    if ">>" in s:
        s = s.split(">>")[0].strip()
    # Удаляем . ! ? : ; в конце строки
    s = re.sub(r'[.!?:;]+$', '', s).strip()
    return s


def normalize_person_name(name: Optional[str]) -> str:
    """
    Нормализует ФИО: удаляет лишние пробелы, приводит к стандартному виду.
    """
    if not name:
        return ""
    # Удаляем множественные пробелы и пробелы по краям
    return " ".join(str(name).strip().split())


def normalize_person_key(name: Optional[str]) -> str:
    """
    Возвращает ключ для словарей AI-оценок (нижний регистр без лишних пробелов).
    """
    return normalize_person_name(name).lower()


_INVALID_FILENAME_CHARS = re.compile(r'[\\/*?:"<>|]')


def report_html_filename(full_name: str) -> str:
    """
    Имя автономного HTML-отчёта по ФИО сотрудника.

    Пример: «Иванов Иван Иванович.html».
    Пробелы сохраняются; заменяются только символы, недопустимые в имени файла.
    """
    name = normalize_person_name(full_name)
    safe = _INVALID_FILENAME_CHARS.sub('_', name).rstrip(' .')
    if not safe:
        safe = 'report'
    return f'{safe}.html'

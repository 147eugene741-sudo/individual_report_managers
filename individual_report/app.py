# app.py
import os
import logging
from flask import Flask, send_from_directory, jsonify, request

# ---------- Настройка логирования ----------
LOG_FILE = os.getenv('LOG_FILE', 'logs/app.log')
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# ---------- Flask-приложение ----------
app = Flask(__name__)

# Добавляем кастомный фильтр escapejs для Jinja2
@app.template_filter('escapejs')
def escapejs_filter(value):
    """Экранирует специальные символы для использования в JavaScript"""
    if not isinstance(value, str):
        value = str(value) if value is not None else ''
    # Экранируем обратные слеши, кавычки и переносы строк
    value = value.replace('\\', '\\\\')
    value = value.replace("'", "\\'")
    value = value.replace('"', '\\"')
    value = value.replace('\n', '\\n')
    value = value.replace('\r', '\\r')
    value = value.replace('</', '<\\/')  # Защита от закрытия script тега
    return value

# Переменные окружения для настройки
DEBUG_MODE = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
FLASK_HOST = os.getenv('FLASK_HOST', '127.0.0.1')
FLASK_PORT = int(os.getenv('FLASK_PORT', 5000))

# ---------- CORS (для локальной разработки) ----------
@app.after_request
def add_cors_headers(response):
    # В production ограничить домены
    allowed_origin = os.getenv('CORS_ALLOWED_ORIGIN', '*')
    response.headers['Access-Control-Allow-Origin'] = allowed_origin
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type'
    response.headers['Access-Control-Allow-Methods'] = 'POST, GET, OPTIONS'
    return response

# ---------- Эндпоинты ----------
@app.route('/reports/<path:filename>')
def serve_report(filename):
    """Раздаёт HTML-отчёты из папки output/"""
    output_dir = os.getenv('OUTPUT_DIR', 'output')
    return send_from_directory(output_dir, filename)

@app.route('/health', methods=['GET'])
def health():
    """Эндпоинт проверки здоровья приложения"""
    return jsonify({'status': 'ok'})

@app.errorhandler(404)
def not_found(error):
    """Обработчик ошибки 404"""
    logger.warning(f'Ресурс не найден: {request.url}')
    return jsonify({'error': 'Ресурс не найден'}), 404

@app.errorhandler(500)
def internal_error(error):
    """Обработчик ошибки 500"""
    logger.error(f'Внутренняя ошибка сервера: {error}')
    return jsonify({'error': 'Внутренняя ошибка сервера'}), 500

# ---------- Запуск ----------
if __name__ == '__main__':
    app.run(debug=DEBUG_MODE, host=FLASK_HOST, port=FLASK_PORT)
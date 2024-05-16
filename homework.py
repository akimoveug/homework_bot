import logging
import os
import sys
import time
from http import HTTPStatus
from logging.handlers import RotatingFileHandler

import requests
from dotenv import load_dotenv
from telebot import TeleBot


load_dotenv()


PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')


RETRY_PERIOD = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

REQUIRED_TOKENS = ('TELEGRAM_TOKEN', 'PRACTICUM_TOKEN', 'TELEGRAM_CHAT_ID')
API_ERROR_KEYS = ('code', 'error')

CHECK_TOKENS_ERROR = ('Отсутствуют переменные окружения {tokens}. '
                      'Программа принудительно остановлена.')
API_CONNECTION_ERROR = ('ошибка запроса к API: {detail_info}. URL: {url}, '
                        'HEADERS: {headers}, PARAMS: {params}')
API_RESPONSE_ERROR = (
    'ошибка запроса к API. Ошибка {code}. Ключи и значения в ответе: '
    '{found_keys_values} URL: {url}, HEADERS: {headers}, PARAMS: {params}'
)
API_KEYS_ERROR = (
    'ошибка запроса к API. Ключи и значения в ответе: {keys_values}'
)
RESPONSE_TYPE_ERROR = 'в ответе пришел не словарь, а {type}'
NO_HOMEWORKS_IN_RESPONSE_ERROR = 'в ответе отсутствует ключ "homeworks".'
HOMEWORKS_TYPE_ERROR = 'в ответе пришел не список, а {type}'
NO_NEW_STATUSES = 'в ответе отсутствуют новые статусы'
HOMEWORK_TYPE_ERROR = 'отдельная работа не в словаре, а в {type}'
HOMEWORK_MISSING_KEYS = 'в ответе не найдены ключи: {keys}'
UNEXPECTED_HOMEWORK_STATUS = 'неожиданный статус у работы - {status}'
HOMEWORK_STATUS_CHANGED_MESSAGE = (
    'Изменился статус проверки работы "{homework_name}". {status}'
)
BOT_SEND_MESSAGE = 'Бот отправил сообщение: {message}'
BOT_SEND_MESSAGE_ERROR = (
    'ошибка при отправке сообщения: {message}. Ошибка: "{error}"'
)
EXCEPTION_TEXT = 'Сбой в работе программы: {error}'

logger = logging.getLogger(__name__)


def check_tokens():
    """Проверка наличия токенов."""
    global_variables = globals()
    tokens_with_none_value = [
        token for token in REQUIRED_TOKENS if global_variables[token] is None
    ]
    if tokens_with_none_value:
        error_message = CHECK_TOKENS_ERROR.format(
            tokens=tokens_with_none_value
        )
        logger.critical(error_message)
        raise ValueError(error_message)


def get_api_answer(timestamp):
    """Получение ответа от API."""
    request_params = dict(
        url=ENDPOINT,
        headers=HEADERS,
        params={'from_date': timestamp}
    )
    try:
        response = requests.get(**request_params)
    except requests.exceptions.RequestException as error:
        raise ConnectionError(API_CONNECTION_ERROR.format(
            detail_info=error,
            **request_params
        ))
    try:
        response_json = response.json()
    except Exception:
        raise RuntimeError(API_RESPONSE_ERROR.format(
            code=response.status_code,
            **request_params
            ))
    if response.status_code == HTTPStatus.OK:
        return response_json
    raise RuntimeError(API_KEYS_ERROR.format(
       keys_values={
           key: item for key, item in response_json.items()
           if key in API_ERROR_KEYS
       },
       **request_params
    ))


def check_response(response):
    """Проверка ответа от API. Возвращает список работ."""
    if not isinstance(response, dict):
        raise TypeError(RESPONSE_TYPE_ERROR.format(type=type(response)))

    if 'homeworks' not in response:
        raise KeyError(
            NO_HOMEWORKS_IN_RESPONSE_ERROR
        )

    homeworks = response['homeworks']
    if not isinstance(homeworks, list):
        raise TypeError(HOMEWORKS_TYPE_ERROR.format(type=type(homeworks)))
    return homeworks


def parse_status(homework):
    """Статус конкретной домашней работы."""
    missing_keys = [
        key for key in ('homework_name', 'status') if key not in homework
    ]
    if missing_keys:
        raise KeyError(HOMEWORK_MISSING_KEYS.format(keys=missing_keys))

    status = homework['status']
    if status not in HOMEWORK_VERDICTS:
        raise ValueError(
            UNEXPECTED_HOMEWORK_STATUS.format(status=status)
        )
    return HOMEWORK_STATUS_CHANGED_MESSAGE.format(
        homework_name=homework['homework_name'],
        status=HOMEWORK_VERDICTS.get(status)
    )


def send_message(bot, message):
    """Отправка сообщения в Telegram."""
    bot_message = bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    logger.debug(BOT_SEND_MESSAGE.format(message=message))
    return bot_message


def main():
    """Основная логика работы бота."""
    check_tokens()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    last_message = ''
    while True:
        try:
            api_answer = get_api_answer(timestamp)
            homeworks = check_response(api_answer)
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message):
                    timestamp = api_answer.get('current_date', timestamp)
            else:
                logger.debug(NO_NEW_STATUSES)
        except Exception as error:
            message = EXCEPTION_TEXT.format(error=error)
            logger.error(message)
            if message != last_message:
                try:
                    if send_message(bot, message):
                        last_message = message
                except Exception:
                    pass
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s, %(levelname)s, %(funcName)s'
               ' - %(lineno)d, %(message)s',
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(
                filename=__file__ + '.log',
                maxBytes=5000000,
                backupCount=3
            )
        ]
    )
    main()

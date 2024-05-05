from http import HTTPStatus
import logging
from logging.handlers import RotatingFileHandler
import os
import sys
import time

from dotenv import load_dotenv
import requests
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

LOGGING_LEVEL = logging.DEBUG
REQUIRED_TOKENS = ('TELEGRAM_TOKEN', 'PRACTICUM_TOKEN', 'TELEGRAM_CHAT_ID')
HOMEWORKS_KEY = 'homeworks'
HOMEWORK_NAME_KEY = 'homework_name'
HOMEWORK_STATUS_KEY = 'status'


CHECK_TOKENS_ERROR = ('Отсутствуют переменные окружения {tokens}. '
                      'Программа принудительно остановлена.')
API_ERROR = 'ошибка запроса к API: {detail_info}'
API_ERROR2 = 'API Практикума недоступно. Ошибка {code}. Запрос к {url}'
RESPONSE_TYPE_ERROR = 'в ответе пришел не словарь, а {type}'
NO_HOMEWORKS_IN_RESPONSE_ERROR = (
    'в ответе отсутствует ключ homeworks. Получен ответ: {response}'
)
HOMEWORKS_TYPE_ERROR = 'в ответе пришел не список, а {type}'
NO_NEW_STATUSES = 'в ответе отсутствуют новые статусы'
HOMEWORK_TYPE_ERROR = 'отдельная работа не в словаре, а в {type}'
UNEXPECTED_HOMEWORK_KEYS = 'неожиданные ключи у работы - {keys}'
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
    """Проверка токенов."""
    global_variables = globals()
    tokens_with_none_value = [
        token for token in REQUIRED_TOKENS if global_variables[token] is None
    ]
    if len(tokens_with_none_value) > 0:
        raise KeyError(
            CHECK_TOKENS_ERROR.format(tokens=', '.join(tokens_with_none_value))
        )


def get_api_answer(timestamp):
    """Получение ответа от API."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
    except requests.exceptions.RequestException as error:
        raise ValueError(API_ERROR.format(detail_info=error))

    if response.status_code in (HTTPStatus.OK, HTTPStatus.BAD_REQUEST):
        return response.json()
    else:
        raise KeyError(
            API_ERROR2.format(
                code=response.status_code, url=response.request.url
            )
        )


def check_response(response):
    """Проверка ответа от API. Возвращает список работ."""
    if not isinstance(response, dict):
        raise TypeError(RESPONSE_TYPE_ERROR.format(type=type(response)))

    if HOMEWORKS_KEY not in response:
        raise KeyError(
            NO_HOMEWORKS_IN_RESPONSE_ERROR.format(response=response)
        )

    homeworks = response[HOMEWORKS_KEY]
    current_date = response.get('current_date')
    if not isinstance(homeworks, list):
        raise TypeError(HOMEWORKS_TYPE_ERROR.format(type=type(homeworks)))
    return homeworks, current_date


def parse_status(homework):
    """Статус конкретной домашней работы."""
    if (HOMEWORK_NAME_KEY or HOMEWORK_STATUS_KEY) not in homework.keys():
        raise KeyError(UNEXPECTED_HOMEWORK_KEYS.format(keys=homework.keys()))
    homework_name = homework[HOMEWORK_NAME_KEY]
    homework_status = homework[HOMEWORK_STATUS_KEY]
    if homework_status not in HOMEWORK_VERDICTS:
        raise KeyError(
            UNEXPECTED_HOMEWORK_STATUS.format(status=homework_status)
        )
    else:
        return HOMEWORK_STATUS_CHANGED_MESSAGE.format(
            homework_name=homework_name,
            status=HOMEWORK_VERDICTS.get(homework_status)
        )


def send_message(bot, message):
    """Отправка сообщения в Telegram.
    Возвращает True если сообщение отправлено.
    """
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.debug(BOT_SEND_MESSAGE.format(message=message))
    except Exception as error:
        logger.error(
            BOT_SEND_MESSAGE_ERROR.format(message=message, error=error),
            exc_info=True
        )
    return True


def main():
    """Основная логика работы бота."""
    logger.setLevel(LOGGING_LEVEL)
    exception_errors = {}
    try:
        check_tokens()
    except Exception as error:
        logger.critical(error)
        sys.exit()
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    while True:
        try:
            homeworks, api_response_time = check_response(
                get_api_answer(timestamp)
            )
            if homeworks:
                message = parse_status(homeworks[0])
                if send_message(bot, message) is True:
                    timestamp = api_response_time
            else:
                logger.debug(NO_NEW_STATUSES)
        except Exception as error:
            message = EXCEPTION_TEXT.format(error=error)
            logger.error(message)
            if str(error) not in exception_errors.keys():
                exception_errors[str(error)] = 'Exception error'
                send_message(bot, message)
        time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    logging.basicConfig(
        format='%(asctime)s, %(levelname)s, %(funcName)s'
               ' - %(lineno)d, %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            RotatingFileHandler(
                filename=__file__ + '.log',
                maxBytes=50000000,
                backupCount=5
            )
        ]
    )
    main()
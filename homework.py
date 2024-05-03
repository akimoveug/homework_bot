import logging
import os
import requests
import sys
import time

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

LOGGING_LEVEL = logging.DEBUG

logger = logging.getLogger(__name__)


class EnvVariableNoValueError(Exception):
    """Ошибка - переменная окружения не имеет значения."""


class ApiError(Exception):
    """Ошибка API Практикума."""


class EmptyResponseError(Exception):
    """Ответ API пустой."""


class ParsingError(Exception):
    """Ошибка извлечения данных о домашней работе."""


def check_tokens():
    """Проверка токенов."""
    try:
        global_variables = globals()
        for token in ('TELEGRAM_TOKEN', 'PRACTICUM_TOKEN', 'TELEGRAM_CHAT_ID'):
            if global_variables[token] is None:
                raise EnvVariableNoValueError(
                    f'отсутсвует обязательная переменная окружения {token}.'
                    ' Программа принудительно остановлена. '
                )
    except Exception as error:
        logger.critical(f'Сбой в работе программы: {error}')
        sys.exit()


def get_api_answer(timestamp):
    """Получение ответа от API."""
    try:
        response = requests.get(
            ENDPOINT,
            headers=HEADERS,
            params={'from_date': timestamp}
        )
        if response.status_code == 200:
            return response.json()
        else:
            raise ApiError(
                f'API Практикума недоступно. Ошибка {response.status_code}.'
            )
    except requests.exceptions.RequestException as error:
        raise ApiError(f'ошибка обращения к API: {error}')


def check_response(response):
    """Проверка ответа от API."""
    try:
        homeworks = response['homeworks']
        last_try_time = response['current_date']
    except KeyError as error:
        raise Exception(
            f'в ответе отсутствует ключ {error}. Получен ответ {response}'
        )

    if not isinstance(homeworks, list):
        raise TypeError('в ответе пришел не список')

    try:
        homework = homeworks[0]
    except IndexError:
        raise EmptyResponseError('в ответе отсутствуют новые статусы')
    else:
        return homework, last_try_time


def parse_status(homework):
    """Статус конкретной домашней работы."""
    try:
        status_message = HOMEWORK_VERDICTS[homework['status']]
        homework_name = homework['homework_name']
    except KeyError as error:
        raise ParsingError(f'неожиданный статус у работы - {error}')
    else:
        return (
            f'Изменился статус проверки работы "{homework_name}". '
            f'{status_message}'
        )


def send_message(bot, message):
    """Отправка сообщения в Telegram."""
    try:
        bot.send_message(chat_id=os.getenv('TELEGRAM_CHAT_ID'), text={message})
    except Exception as error:
        logger.error(f'Ошибка при отправке в телеграм. "{error}"')
    else:
        logger.debug(f'Бот отправил сообщение: "{message}"')


def main():
    """Основная логика работы бота."""
    logger.setLevel(LOGGING_LEVEL)
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter('%(asctime)s, %(levelname)s, %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    bot = TeleBot(token=TELEGRAM_TOKEN)
    timestamp = int(time.time())
    check_tokens()
    error_occurred = False
    while True:
        try:
            homework, timestamp = check_response(get_api_answer(timestamp))
            message = parse_status(homework)
            send_message(bot, message)
            error_occurred = False
        except EmptyResponseError as error:
            logger.debug(error)
            pass
        except Exception as error:
            error_message = f'Сбой в работе программы: {error}'
            logger.error(error_message)
            if error_occurred is not True:
                error_occurred = True
                send_message(bot, error_message)
        finally:
            time.sleep(RETRY_PERIOD)


if __name__ == '__main__':
    main()

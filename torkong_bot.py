import datetime as dt
import os
import time
import logging

import requests
import telegram
from cryptography.hazmat.backends import default_backend
from cryptography.x509 import load_der_x509_crl, load_pem_x509_crl
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    datefmt='%d-%b-%y %H:%M:%S',
    filename='torkong_bot.log',
    level=logging.INFO
)

WATCH_PERIOD = int(os.getenv('WATCH_PERIOD'))
PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
BASE_URL = 'https://praktikum.yandex.ru/api/user_api/homework_statuses/'

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

CRL_URLS = os.getenv('CRL_URLS_LIST').split(' ')
CRL_OVERLAP_TIME = int(os.getenv('CRL_OVERLAP_TIME'))


def parse_homework_status(homework):
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status and homework_name:
        if homework_status == 'rejected':
            verdict = 'Code reviewer found errors in homework.'
        elif homework_status == 'approved':
            verdict = 'It is accepted! You can start next lesson!'
        else:
            raise ValueError('Bad "status" key value')
        return f'Homework "{homework_name}" is checked!\n\n{verdict}'
    else:
        raise KeyError('No "homework_name" and/or "status" key in argument.')


def get_homework_statuses(current_timestamp):
    headers = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}
    from_date = current_timestamp
    params = {'from_date': from_date}
    try:
        homework_statuses = requests.get(BASE_URL,
                                         params=params,
                                         headers=headers)
        homework_statuses.raise_for_status()
    except requests.exceptions.RequestException as error:
        raise SystemExit(error)
    return homework_statuses.json()


def check_crl_status(crl_urls):
    crl_status = {'server_errors': [],
                  'crl_errors': []}
    time_delta = dt.timedelta(minutes=CRL_OVERLAP_TIME)
    for url in crl_urls:
        crl_file = url.split('/')[-1]
        try:
            response = requests.get(url)
            response.raise_for_status()
        except requests.exceptions.RequestException as error:
            crl_status['server_errors'].append(
                f'CRL {crl_file} getting error - {error}'
            )
            logging.error(f'CRL {crl_file} getting error - {error}')
            continue
        try:
            crl = load_der_x509_crl(response.content,
                                    default_backend())
        except ValueError:
            crl = load_pem_x509_crl(response.content,
                                    default_backend())
        time_to_update = crl.next_update - dt.datetime.now()
        if time_to_update < time_delta:
            crl_status['crl_errors'].append(crl_file)

    return crl_status


def parse_crl_status(errors):
    message_text = ''
    server_errors = errors.get('server_errors')
    crl_errors = errors.get('crl_errors')
    if server_errors:
        message_text = 'Infrastructure errors: '
        for error in server_errors:
            message_text += f'\n{error}'
    if crl_errors:
        text = "\nIt's time to update crl: "
        for crl_file in crl_errors:
            if crl_file == crl_errors[-1]:
                message_text += f'{text}{crl_file}.'
            else:
                message_text += f'{text}{crl_file}, '
    return message_text


def send_message(message, bot):
    return bot.send_message(chat_id=CHAT_ID, text=message)


def main():
    logging.info('BOT was started')
    # current_timestamp = int(time.time())
    bot = telegram.Bot(token=TELEGRAM_TOKEN)

    while True:
        try:
            # Check Yandex.Practicum homework status
            # new_homework = get_homework_statuses(current_timestamp)
            # if new_homework.get('homeworks'):
            #     send_message(
            #         parse_homework_status(new_homework.get('homeworks')[0]),
            #         bot
            #     )
            # current_timestamp = new_homework.get('current_date')

            is_crl_updated = check_crl_status(CRL_URLS)
            if is_crl_updated['server_errors'] or is_crl_updated['crl_errors']:
                send_message(parse_crl_status(is_crl_updated), bot)

            time.sleep(WATCH_PERIOD)

        except KeyboardInterrupt:
            logging.info('BOT stopped with keyboard')
            break

        except SystemExit as error:
            send_message(f'BOT is dropped with error: {error}', bot)
            logging.error(f'BOT is dropped with error: {error}')
            time.sleep(WATCH_PERIOD)
            continue

        except Exception as error:
            send_message(f'BOT is dropped with error: {error}', bot)
            logging.error(f'BOT is dropped down with error: {error}')
            time.sleep(WATCH_PERIOD)
            continue


if __name__ == '__main__':
    main()

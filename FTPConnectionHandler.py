#!/usr/bin/python3

from threading import Thread
from logger import log


class FTPThreadHandler(Thread):
    BUFFER_SIZE = 4110
    ANSWERS = {
        331: b'331 Need account for login.',
        530: b'530 Not logged in.',
        230: b'230 User logged in, proceed.',
        200: b'200 Command okay.',
        500: b'500 Syntax error, command unrecognized.'
    }

    def __init__(self, connection, root_dir, users):
        Thread.__init__(self)
        self.client_socket, self.address = connection
        self.root_dir = root_dir
        self.users = users
        self.username = None
        self.passive_mode = False
        self.current_dir = root_dir

    @staticmethod
    def get_command_name(command_text):
        return command_text[:4].strip().upper().decode('ascii')

    @staticmethod
    def get_readable_command(command_text):
        return command_text[:len(command_text) - 1].decode('ascii')

    def run(self):
        log('{a[0]}:{a[1]} connected'.format(a=self.address))

        self.client_socket.send(b'220 Welcome!\r\n')
        while True:
            try:
                command_text = self.client_socket.recv(FTPThreadHandler.BUFFER_SIZE)
                if command_text:
                    log('received: {}'.format(FTPThreadHandler.get_readable_command(command_text)))
                    command_handler = getattr(self, FTPThreadHandler.get_command_name(command_text))
                    command_handler(command_text)
            except ConnectionAbortedError:
                log('connection aborted')
                return
            except ConnectionError as e:
                log('error: connection error: {}'.format(e))
            except AttributeError:
                log('error: unknown command: {}'.format(command_text))
                self.send_answer(500)

    def send_answer(self, code):
        if code in FTPThreadHandler.ANSWERS:
            self.client_socket.send(FTPThreadHandler.ANSWERS[code] + b'\r\n')

    def USER(self, command_text):
        username = (command_text.split()[1]).decode('ascii')
        if username in self.users:
            self.username = username
            log('{}: username accepted'.format(username))
            self.send_answer(331)
        else:
            log('{}: username not found'.format(username))
            self.send_answer(530)

    def PASS(self, command_text):
        password = (command_text.split()[1]).decode('ascii')
        log_mesage = 'user {}, password {}'.format(self.username, password)
        if self.users.get(self.username) == password:
            log(log_mesage + ': access granted')
            self.send_answer(230)
        else:
            log(log_mesage + ': access denied')
            self.send_answer(530)

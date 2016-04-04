#!/usr/bin/python3

from threading import Thread
from logger import log


class FTPThreadHandler(Thread):
    BUFFER_SIZE = 4110

    def __init__(self, connection, root_dir):
        Thread.__init__(self)
        self.client_socket, self.address = connection
        self.root_dir = root_dir
        self.passive_mode = False
        self.current_dir = root_dir

    @staticmethod
    def get_command_name(command_text):
        return command_text[:4].strip().upper().decode('ascii')

    def run(self):
        log('{a[0]}:{a[1]} connected'.format(a=self.address))

        self.client_socket.send(b'220 Welcome!\r\n')
        while True:
            try:
                command_text = self.client_socket.recv(FTPThreadHandler.BUFFER_SIZE)
            except ConnectionError as e:
                log('error: connection error: {}'.format(e))
                return

            log('received: {}'.format(command_text))
            try:
                command_handler = getattr(self, FTPThreadHandler.get_command_name(command_text))
                command_handler(command_text)
            except AttributeError as e:
                log('error: unknown command: {}'.format(command_text))
                self.client_socket.send(b'500 Command unrecognized.\r\n')

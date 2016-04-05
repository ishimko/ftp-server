import socket
from threading import Thread, Lock
from logger import log


class DataConnection(Thread):
    def __init__(self, connection, send_answer):
        if isinstance(connection, tuple):
            self.passive_mode = False
            self.client = connection
        else:
            self.passive_mode = True
            self.passive_connection = connection
        self.aborted = False
        self.data = bytes()
        self.data_socket = None
        self.lock = Lock()
        self.send_answer = send_answer
        Thread.__init__(self)

    def set_data(self, data):
        self.data = data

    def is_aborted(self):
        self.lock.acquire()
        result = self.aborted
        self.lock.release()
        return result

    def abort(self):
        self.lock.acquire()
        self.aborted = True
        self.lock.release()

    def init_data_socket(self):
        if self.passive_mode:
            self.data_socket, self.client = self.passive_connection.accept()
            log('{a[0]}:{a[1]} connected'.format(a=self.client))
        else:
            self.data_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
            self.data_socket.connect(self.client)

    def run(self):
        log('sending to {a[0]}:{a[1]}'.format(a=self.client))
        sent_data_size = 0
        block_number = 1
        while (not self.is_aborted()) and (sent_data_size < len(self.data)):
            block_to_send = self.data[(block_number - 1) * 100: block_number * 100]
            block_number += 1
            sent_data_size += len(block_to_send)
            self.data_socket.send(block_to_send)

        self.stop()

        log('sending to {a[0]}:{a[1]} complete'.format(a=self.client))

    def stop(self):
        self.abort()
        self.data_socket.close()
        if self.passive_mode:
            self.passive_connection.close()

        self.send_answer(226)

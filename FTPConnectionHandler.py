from threading import Thread, Lock
from logger import log
from DataConnection import DataConnection
import os
import time
import socket


class FTPThreadHandler(Thread):
    BUFFER_SIZE = 4110
    ANSWERS = {
        331: 'Need account for login.',
        530: 'Not logged in.',
        230: 'User logged in, proceed.',
        200: 'Command okay.',
        500: 'Syntax error, command unrecognized.',
        221: 'Service closing control connection.',
        502: 'Command not implemented.',
        227: 'Entering passive mode ',
        150: 'About to open data connection.',
        226: 'Closing data connection.'
    }

    def __init__(self, connection, root_dir, users):
        Thread.__init__(self)
        self.client_socket, self.address = connection
        self.root_dir = root_dir
        self.users = users
        self.username = None
        self.current_dir = root_dir
        self.is_closed = False
        self.passive_connection = None
        self.data_connection = None
        self.active_ip = None
        self.active_port = None
        self.lock = Lock()

    @staticmethod
    def get_command_name(command_text):
        return command_text[:4].strip().upper().decode('ascii')

    @staticmethod
    def get_readable_command(command_text):
        return command_text[:len(command_text) - 1].decode('ascii')

    def run(self):
        log('{a[0]}:{a[1]} connected'.format(a=self.address))
        command_text = None

        self.client_socket.send(b'220 Welcome!\r\n')
        while not self.is_closed:
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

    def send_answer(self, code, msg=''):
        self.lock.acquire()
        if code in FTPThreadHandler.ANSWERS:
            self.client_socket.send((str(code) + ' ' + FTPThreadHandler.ANSWERS[code] + msg + '\r\n').encode('ascii'))
        self.lock.release()

    def USER(self, command_text):
        username = (command_text.split()[1]).decode('ascii')
        log_message = 'username {}'.format(username)
        if username in self.users:
            self.username = username
            log(log_message + ': accepted')
            self.send_answer(331)
        else:
            log(log_message + ': username not found')
            self.send_answer(530)

    def PASS(self, command_text):
        password = (command_text.split()[1]).decode('ascii')
        log_message = 'user: {}, password: {}'.format(self.username, password)
        if self.users.get(self.username) == password:
            log(log_message + ': access granted')
            self.send_answer(230)
        else:
            log(log_message + ': access denied')
            self.send_answer(530)

    def QUIT(self, _):
        self.send_answer(221)
        self.client_socket.close()
        self.close()
        log('{} disconnected'.format(self.username))

    def NOOP(self, _):
        self.send_answer(200)

    def SYST(self, _):
        self.send_answer(215, 'UNIX Type: L8')

    def PORT(self, command_text):
        if self.passive_connection:
            self.passive_connection.close()
            self.passive_connection = None
        received_bytes = command_text[5:].split(b',')
        self.active_ip = b'.'.join(received_bytes[:4])
        self.active_port = (int(received_bytes[4]) << 8) + int(received_bytes[5])
        self.send_answer(200)

    def PASV(self, _):
        self.passive_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.passive_connection.bind(('', 0))
        self.passive_connection.listen(1)
        ip, port = self.passive_connection.getsockname()
        log('ready for connect on {}:{}'.format(ip, port))
        self.send_answer('({})'.format(FTPThreadHandler.get_address_str(ip, port)))

    @staticmethod
    def get_address_str(ip, port):
        port_str = port.to_bytes(2, byteorder='big')
        return '{},{port[0]},{port[1]}'.format(','.join(ip.split('.')), port=port_str)

    def LIST(self, _):
        self.send_answer(150)
        log('sending list of {}'.format(self.current_dir))
        dir_listing = self.get_dir_listing()
        if self.passive_connection:
            self.data_connection = DataConnection(self.passive_connection, self.send_answer)
        else:
            self.data_connection = DataConnection((self.active_ip, self.active_port), self.send_answer)
        self.data_connection.set_data(dir_listing)
        self.data_connection.init_data_socket()
        self.data_connection.daemon = True
        self.data_connection.start()

    def ABOR(self, _):
        if not self.data_connection.is_aborted():
            self.data_connection.stop()

    def close(self):
        self.is_closed = True

    def get_dir_listing(self):
        result = b''
        for dir_entry in os.listdir(self.current_dir):
            list_entry = FTPThreadHandler.get_list_entry(dir_entry)
            result += list_entry + b'\r\n'
        return result

    @staticmethod
    def get_list_entry(dir_entry):
        stat_info = os.stat(dir_entry)
        full_mode = 'rwx' * 3
        mode = ''
        for i in range(9):
            mode += full_mode[i] if ((stat_info.st_mode >> (8 - i)) & 1) else '-'
        d = 'd' if (os.path.isdir(dir_entry)) else '-'
        entry_time = time.strftime(' %b %d %H:%M ', time.gmtime(stat_info.st_mtime))
        return (d + mode + ' ' + str(stat_info.st_size) + entry_time + os.path.basename(dir_entry)).encode('ascii')

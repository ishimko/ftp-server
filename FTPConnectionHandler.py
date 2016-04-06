from threading import Thread, Lock
from logger import log
from DataConnection import DataConnection
import os
import time
import socket
from pwd import getpwuid


class FTPThreadHandler(Thread):
    BUFFER_SIZE = 4110
    IP_FOR_PASSIVE = '127.0.0.1'
    ANSWERS = {
        331: 'Need account for login.',
        530: 'Not logged in.',
        230: 'User logged in, proceed.',
        200: 'Command okay.',
        500: 'Syntax error, command unrecognized.',
        221: 'Service closing control connection.',
        502: 'Command not implemented.',
        227: 'Entering passive mode',
        150: 'About to open data connection.',
        226: 'Closing data connection.',
        215: '',
        450: 'Requested file action not taken.',
        250: 'Requested file action okay, completed.',
        257: '',
        213: '',
        220: 'Welcome!',

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
        self.mode = 'I'

    @staticmethod
    def get_command_name(command_text):
        return command_text[:4].strip().upper().decode('ascii')

    @staticmethod
    def get_readable_command(command_text):
        return command_text[:-2].decode('utf-8')

    def run(self):
        log('{a[0]}:{a[1]} connected'.format(a=self.address))
        command_text = None

        self.send_answer(220)
        while not self.is_closed:
            try:
                command_text = self.client_socket.recv(FTPThreadHandler.BUFFER_SIZE)
                if command_text:
                    readable_command = FTPThreadHandler.get_readable_command(command_text)
                    log('received: {}'.format(readable_command))
                    command_handler = getattr(self, FTPThreadHandler.get_command_name(command_text))
                    command_handler(readable_command[4:].strip())
            except ConnectionAbortedError:
                log('connection aborted')
                return
            except ConnectionError as e:
                log('error: connection error: {}'.format(e))
            except AttributeError:
                log('error: unknown command: {}'.format(FTPThreadHandler.get_command_name(command_text)))
                self.send_answer(500)

    def send_answer(self, code, msg=''):
        self.lock.acquire()
        if code in FTPThreadHandler.ANSWERS:
            self.client_socket.send((str(code) + ' ' + FTPThreadHandler.ANSWERS[code] + msg + '\r\n').encode('ascii'))
        self.lock.release()

    def USER(self, command_text):
        username = command_text
        log_message = 'username {}'.format(username)
        if username in self.users:
            self.username = username
            log(log_message + ': accepted')
            self.send_answer(331)
        else:
            log(log_message + ': username not found')
            self.send_answer(530)

    def PASS(self, command_text):
        password = command_text
        log_message = 'user: {}, password: {}'.format(self.username, password)
        if self.users.get(self.username) == password:
            log(log_message + ': access granted')
            self.send_answer(230)
        else:
            log(log_message + ': access denied')
            self.username = ''
            self.send_answer(530)

    def QUIT(self, _):
        self.send_answer(221)
        self.client_socket.close()
        self.close()
        log('{} disconnected'.format(self.username))

    def NOOP(self, _):
        self.send_answer(200)

    def SYST(self, _):
        if not self.username:
            self.send_answer(530)
            return
        log('sending system type')
        self.send_answer(215, 'UNIX Type: L8')

    def PORT(self, command_text):
        if not self.username:
            self.send_answer(530)
            return

        if self.passive_connection:
            self.passive_connection.close()
            self.passive_connection = None
        received_bytes = command_text.split(',')
        self.active_ip = ('.'.join(received_bytes[:4])).encode('ascii')
        self.active_port = (int(received_bytes[4]) << 8) | int(received_bytes[5])
        log('client info for active connection: {}:{}'.format(self.active_ip, self.active_port))
        self.send_answer(200)

    def PASV(self, _):
        if not self.username:
            self.send_answer(530)
            return

        self.passive_connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.passive_connection.bind((FTPThreadHandler.IP_FOR_PASSIVE, 0))
        self.passive_connection.listen(1)
        ip, port = self.passive_connection.getsockname()
        log('ready for connect on {}:{}'.format(ip, port))
        self.send_answer(227, '({})'.format(FTPThreadHandler.get_address_str(ip, port)))

    @staticmethod
    def get_address_str(ip, port):
        port_str = port.to_bytes(2, byteorder='big')
        return '{},{port[0]},{port[1]}'.format(','.join(ip.split('.')), port=port_str)

    def LIST(self, _):
        if not self.username:
            self.send_answer(530)
            return

        self.send_answer(150)
        log('sending list of {}'.format(self.current_dir))
        dir_listing = self.get_dir_listing()
        if self.passive_connection:
            self.data_connection = DataConnection(self.passive_connection, self.send_answer)
        else:
            self.data_connection = DataConnection((self.active_ip, self.active_port), self.send_answer)
        self.data_connection.set_data(dir_listing)
        self.data_connection.init_data_socket()
        self.data_connection.start()

    def ABOR(self, _):
        if not self.data_connection.is_aborted():
            self.data_connection.stop()

    def TYPE(self, mode):
        if not self.username:
            self.send_answer(530)
            return

        self.mode = mode
        if self.mode == 'I':
            log('switching to binary mode')
        else:
            log('switching to text mode')
        self.send_answer(200)

    def RETR(self, command_text):
        if not self.username:
            self.send_answer(530)
            return

        filename = os.path.join(self.current_dir, command_text)
        log('downloading ' + filename)

        try:
            if self.mode == 'I':
                f = open(filename, 'rb')
                file_content = f.read()
            else:
                f = open(filename, 'r')
                file_content = f.read().encode('ascii')
        except IOError as e:
            self.send_answer(450)
            log('reading {} failed: {}'.format(filename, e))
            return

        self.send_answer(150)
        if self.passive_connection:
            self.data_connection = DataConnection(self.passive_connection, self.send_answer)
        else:
            self.data_connection = DataConnection((self.active_ip, self.active_port), self.send_answer)
        self.data_connection.set_data(file_content)
        self.data_connection.init_data_socket()
        self.data_connection.start()

    def STOR(self, command_text):
        if not self.username:
            self.send_answer(530)
            return

        filename = os.path.join(self.current_dir, command_text)
        log('uploading ' + filename)

        try:
            if self.mode == 'I':
                f = open(filename, 'wb')
            else:
                f = open(filename, 'w')
        except IOError as e:
            self.send_answer(450)
            log('sending {} failed: {}'.format(filename, e))
            return

        self.send_answer(150)
        if self.passive_connection:
            self.data_connection = DataConnection(self.passive_connection, self.send_answer, False)
        else:
            self.data_connection = DataConnection((self.active_ip, self.active_port), self.send_answer, False)
        self.data_connection.init_data_socket()
        self.data_connection.set_out_file(f)
        self.data_connection.start()

    def REIN(self, _):
        log('reinitialization')
        if self.data_connection:
            self.data_connection.stop()
        if self.passive_connection:
            self.passive_connection.close()
            self.passive_connection = None
        self.username = ''
        self.mode = 'I'
        self.current_dir = self.root_dir

    @staticmethod
    def safe_path_join(root, path):
        return os.path.join(root, path if not path[0] == '/' else path[1:])

    def DELE(self, command_text):
        if not self.username:
            self.send_answer(530)
            return

        filename = FTPThreadHandler.safe_path_join(self.root_dir, command_text)

        log_message = '{}: '.format(filename)
        try:
            os.remove(filename)
            self.send_answer(250)
            log(log_message + 'removed')
        except IOError as e:
            self.send_answer(450)
            log(log_message + 'removing failed: \n{}'.format(e))

    def MKD(self, command_text):
        if not self.username:
            self.send_answer(530)
            return

        dirname = FTPThreadHandler.safe_path_join(self.current_dir, command_text)
        log_message = '{}: '.format(dirname)
        try:
            os.mkdir(dirname, mode=0o777)
            self.send_answer(257, dirname)
            log(log_message + 'created')
        except IOError as e:
            self.send_answer(450)
            log(log_message + 'creating failed: \n{}'.format(e))

    def RMD(self, command_text):
        if not self.username:
            self.send_answer(530)
            return
        if command_text[0] == '/':
            dirname = FTPThreadHandler.safe_path_join(self.root_dir, command_text)
        else:
            dirname = FTPThreadHandler.safe_path_join(self.current_dir, command_text)
        log_message = 'dir {}: '.format(dirname)
        try:
            os.rmdir(dirname)
            self.send_answer(250)
            log(log_message + 'removed')
        except IOError as e:
            log(log_message + 'removing failed: \n'.format(e))
            self.send_answer(450)

    def CDUP(self, _):
        if not self.username:
            self.send_answer(530)
            return

        if not os.path.samefile(self.current_dir, self.root_dir):
            self.current_dir = os.path.abspath(os.path.join(self.current_dir, '..'))
        log('new working directory: {}'.format(self.current_dir))
        self.send_answer(200)

    def PWD(self, _):
        if not self.username:
            self.send_answer(530)
            return
        log('sending current directory')
        working_dir = os.path.relpath(self.current_dir, self.root_dir)
        if working_dir == '.':
            working_dir = '/'
        else:
            working_dir = '/' + working_dir
        self.send_answer(257, '"{}"'.format(working_dir))

    def CWD(self, command_text):
        if not self.username:
            self.send_answer(530)
            return

        dirname = command_text
        if dirname == '/':
            new_path = self.root_dir
        elif dirname[0] == '/':
            new_path = os.path.join(self.root_dir, dirname[1:])
        else:
            new_path = os.path.abspath(os.path.join(self.current_dir, dirname))
            if not (os.path.abspath(self.root_dir) in os.path.abspath(new_path)):
                new_path = self.root_dir
        if os.path.isdir(new_path):
            self.current_dir = new_path
            log('new working directory: {}'.format(self.current_dir))
            self.send_answer(250)
        else:
            log('not valid path: {}'.format(new_path))
            self.send_answer(550)

    def SIZE(self, command_text):
        if not self.username:
            self.send_answer(530)
            return

        filename = command_text
        log('sending size of {}'.format(filename))
        try:
            size = os.path.getsize(filename)
            msg = str(size)
            self.send_answer(213, msg)
        except IOError as e:
            self.send_answer(450)
            log('getting size of {} failed:\n{}'.format(filename, e))

    def NLIST(self, _):
        if not self.username:
            self.send_answer(530)
            return

        self.send_answer(150)
        log('sending short list of {}'.format(self.current_dir))
        dir_listing = self.get_dir_listing(short=True)
        if self.passive_connection:
            self.data_connection = DataConnection(self.passive_connection, self.send_answer)
        else:
            self.data_connection = DataConnection((self.active_ip, self.active_port), self.send_answer)
        self.data_connection.set_data(dir_listing)
        self.data_connection.init_data_socket()
        self.data_connection.start()

    def close(self):
        self.is_closed = True

    def get_dir_listing(self, short=False):
        result = b''
        for dir_entry in os.listdir(self.current_dir):
            if short:
                list_entry = dir_entry
            else:
                list_entry = FTPThreadHandler.get_list_entry(os.path.join(self.current_dir, dir_entry))
            list_entry = list_entry.encode('utf-8')
            result += list_entry + b'\r\n'
        return result

    @staticmethod
    def get_file_owner(stat_info):
        return getpwuid(stat_info.st_uid).pw_name

    @staticmethod
    def get_file_group(stat_info):
        return getpwuid(stat_info.st_gid).pw_name

    @staticmethod
    def get_list_entry(dir_entry):
        stat_info = os.stat(dir_entry)
        full_mode = 'rwx' * 3
        mode = ''
        user = FTPThreadHandler.get_file_owner(stat_info)
        group = getpwuid(stat_info.st_gid).pw_name
        for i in range(9):
            mode += full_mode[i] if ((stat_info.st_mode >> (8 - i)) & 1) else '-'
        d = 'd' if (os.path.isdir(dir_entry)) else '-'
        entry_time = time.strftime('%b %d %H:%M', time.gmtime(stat_info.st_mtime))
        return ' '.join([d + mode, str(stat_info.st_nlink), user, str(stat_info.st_size), entry_time,
                         os.path.basename(dir_entry)])

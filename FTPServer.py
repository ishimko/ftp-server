#!/usr/bin/python3
from threading import Thread
import socket
import os
from FTPConnectionHandler import FTPThreadHandler
from logger import log


class FTPServer(Thread):
    def __init__(self, ip='', port=21):
        Thread.__init__(self)
        self.IP = ip
        self.port = port
        self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.serverSocket.bind((ip, port))

    def run(self):
        log('started on port {}'.format(self.port))

        self.serverSocket.listen(1)
        while True:
            client_thread = FTPThreadHandler(self.serverSocket.accept(), os.getcwd())
            client_thread.daemon = True
            client_thread.start()

    def stop(self):
        self.serverSocket.close()

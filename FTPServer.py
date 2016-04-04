#!/usr/bin/python3
from threading import Thread
import socket
import os
from FTPConnectionHandler import FTPThreadHandler
from logger import log


class FTPServer(Thread):
    def __init__(self, users_file='database.dat', ip='', port=21):
        Thread.__init__(self)
        self.IP = ip
        self.port = port
        self.users = FTPServer.read_users(users_file)
        self.serverSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP)
        self.serverSocket.bind((ip, port))

    def run(self):
        log('started on port {}'.format(self.port))

        self.serverSocket.listen(1)
        while True:
            client_thread = FTPThreadHandler(self.serverSocket.accept(), os.getcwd(), self.users)
            client_thread.daemon = True
            client_thread.start()

    def stop(self):
        self.serverSocket.close()

    @staticmethod
    def read_users(users_file):
        users = {}
        for user_entry in open(users_file):
            user_entry = user_entry.split()
            if len(user_entry) > 1:
                users[user_entry[0]] = user_entry[1]
        return users

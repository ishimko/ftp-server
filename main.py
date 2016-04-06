#!/usr/bin/python3

from FTPServer import FTPServer
from logger import log


if __name__ == '__main__':
    ftpServer = FTPServer()
    ftpServer.daemon = True
    ftpServer.start()
    try:
        input('**press Ctrl+C to stop**\n')
    except KeyboardInterrupt:
        ftpServer.stop()
        log('server stopped')

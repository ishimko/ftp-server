from FTPServer import FTPServer

if __name__ == '__main__':
    ftpServer = FTPServer()
    ftpServer.daemon = True
    ftpServer.start()
    try:
        input('\t\tpress Ctrl+C to stop\n')
    except KeyboardInterrupt:
        ftpServer.stop()
        print('server stopped')
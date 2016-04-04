import time


def log(msg):
    print('{}: {}'.format(time.strftime("%H:%M:%S", time.localtime()), msg))

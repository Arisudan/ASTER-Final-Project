from __future__ import annotations

import multiprocessing as mp


def startJarvis(wake_queue):
    print("Process 1 is running.")
    from main import start

    start(wake_queue)


def listenHotword(wake_queue):
    print("Process 2 is running.")
    from Engine.hotword import hotword

    hotword(wake_queue)


if __name__ == "__main__":
    mp.freeze_support()
    wake_queue = mp.Queue()

    p1 = mp.Process(target=startJarvis, args=(wake_queue,))
    p2 = mp.Process(target=listenHotword, args=(wake_queue,))
    p1.start()
    p2.start()
    p1.join()
    if p2.is_alive():
        p2.terminate()
    p2.join()
    print("system stop")

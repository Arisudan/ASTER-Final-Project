import os
import subprocess

import eel

from Engine.Features import *
from Engine.command import *
from Engine.auth import recoganize


@eel.expose
def init():
    try:
        subprocess.call([r'device.bat'])
    except Exception:
        pass

    try:
        eel.hideLoader()
    except Exception:
        pass

    speak("Ready for Face Authentication")
    flag = recoganize.AuthenticateFace()

    if flag == 1:
        try:
            eel.hideFaceAuth()
        except Exception:
            pass
        speak("Face Authentication Successful")
        try:
            eel.hideFaceAuthSuccess()
        except Exception:
            pass
        speak("Hello, Welcome Sir, How can i Help You ?")
        try:
            eel.hideStart()
        except Exception:
            pass
        playAssistantSound()
    else:
        speak("Face Authentication Fail")


def start():
    eel.init('www')
    db_init()
    playAssistantSound()
    os.system('start msedge.exe --app="http://localhost:8000/index.html"')
    eel.start('index.html', mode=None, host='localhost', block=True)

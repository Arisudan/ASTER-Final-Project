import re

with open('main.py', 'r', encoding='utf-8') as f:
    main_py = f.read()

main_py = main_py.replace('subprocess.call([r"device.bat"], cwd=str(BASE_DIR))', 'subprocess.Popen([r"device.bat"], cwd=str(BASE_DIR), shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)')

with open('main.py', 'w', encoding='utf-8') as f:
    f.write(main_py)
print("Updated main.py to not block on device.bat")

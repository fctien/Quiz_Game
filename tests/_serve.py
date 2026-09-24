"""測試用：把 app 跑在指定的埠上(app.py 本身寫死 5000,測試要另外開)"""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT)); os.chdir(ROOT)
import app as A

A.leaderboard.init(); A.classroom.init()
A.app.run(host="127.0.0.1", port=int(sys.argv[1]), debug=False, threaded=True)

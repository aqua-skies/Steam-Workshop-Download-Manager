import os, tempfile, sys, faulthandler, time
os.environ["APPDATA"]=tempfile.mkdtemp(prefix="swdm_dbg2_")
os.environ["PYTHONUTF8"]="1"; os.environ["QT_QPA_PLATFORM"]="offscreen"
sys.path.insert(0,".")
from PySide6.QtWidgets import QApplication
from swdm.core.config import ensure_dirs
from swdm.core.logger import setup_logger
from swdm.gui.main_window import MainWindow
setup_logger("WARNING"); ensure_dirs()
app=QApplication.instance() or QApplication(sys.argv)
win=MainWindow(); win.show(); app.processEvents()
win.svc.refresh_engine = lambda: None
win.svc.refresh_api = lambda: None
st=win.settings_tab
faulthandler.dump_traceback_later(8, exit=True)
print("DBG calling _apply_all", flush=True)
st._apply_all()
print("DBG done", flush=True)

import os, tempfile, sys
os.environ["APPDATA"]=tempfile.mkdtemp(prefix="swdm_dbg_")
os.environ["PYTHONUTF8"]="1"; os.environ["QT_QPA_PLATFORM"]="offscreen"
sys.path.insert(0,".")
print("DBG start", flush=True)
from PySide6.QtWidgets import QApplication
from swdm.core.config import ensure_dirs
from swdm.core.logger import setup_logger
from swdm.gui.main_window import MainWindow
setup_logger("WARNING"); ensure_dirs()
app=QApplication.instance() or QApplication(sys.argv)
win=MainWindow(); win.show(); app.processEvents()
print("DBG win ready", flush=True)
win.svc.refresh_engine = lambda: None
win.svc.refresh_api = lambda: None
st=win.settings_tab
st.channel_combo.setCurrentIndex(1)
app.processEvents()
print("DBG before _apply_all", flush=True)
st._apply_all()
app.processEvents()
print("DBG after _apply_all OK", flush=True)
print("DBG channel=", repr(win.svc.config.get("download","channel",default="")), flush=True)
st.debug_panel_check.setChecked(True)
st._apply_all()
app.processEvents()
print("DBG debug=", bool(win.svc.config.get("logging","show_debug_panel",default=False)), flush=True)

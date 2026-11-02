import os
import sys
import json
import ctypes
from pathlib import Path
from datetime import datetime, date
from ctypes import wintypes

from dotenv import load_dotenv
from openai import OpenAI
from PySide6.QtCore import Qt, QTimer, QThread, Signal, QDate
from PySide6.QtGui import QPixmap, QFont, QAction
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QTextEdit, QLineEdit, QPushButton, QFrame, QMessageBox, QCalendarWidget,
    QListWidget, QListWidgetItem, QTimeEdit, QCheckBox, QSystemTrayIcon,
    QMenu, QInputDialog
)

ROOT = Path(__file__).parent
DATA_FILE = ROOT / "data" / "schedule.json"
load_dotenv(ROOT / ".env")

SYSTEM_PROMPT = """
You are a friendly, playful, encouraging desktop AI companion with a gentle
tsundere anime office-worker personality. Help the user learn and stay organized.
Be warm, patient, lightly teasing, and respectful. Never shame the user for resting.
Do not claim to be human or to have real feelings. Keep answers clear and useful.
"""

DEFAULT_DATA = {
    "tasks": [
        {
            "id": "starter-1",
            "title": "Study / work time",
            "time": "20:00",
            "days": [0, 1, 2, 3, 4, 5, 6],
            "message": "Hmph! It's work time, good boy~ Let's focus together. ♡",
            "enabled": False
        }
    ],
    "settings": {
        "start_with_windows": False,
        "show_over_fullscreen": False,
        "remind_once_per_day": True
    }
}

def load_data():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        save_data(DEFAULT_DATA)
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        data.setdefault("tasks", [])
        data.setdefault("settings", DEFAULT_DATA["settings"].copy())
        return data
    except (json.JSONDecodeError, OSError):
        return json.loads(json.dumps(DEFAULT_DATA))

def save_data(data):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

def is_windows_fullscreen():
    """Best-effort Windows check: is the foreground window covering a monitor?"""
    if sys.platform != "win32":
        return False
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return False
        monitor = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST

        class MONITORINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD),
            ]

        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return False
        a, b = rect, info.rcMonitor
        return (
            abs(a.left - b.left) <= 2 and abs(a.top - b.top) <= 2
            and abs(a.right - b.right) <= 2 and abs(a.bottom - b.bottom) <= 2
        )
    except Exception:
        return False

class ReplyWorker(QThread):
    finished_reply = Signal(str)
    failed = Signal(str)

    def __init__(self, messages):
        super().__init__()
        self.messages = messages

    def run(self):
        try:
            key = os.getenv("OPENAI_API_KEY", "").strip()
            if not key:
                raise RuntimeError("Add your API key to the .env file first.")
            client = OpenAI(api_key=key)
            model = os.getenv("OPENAI_MODEL", "gpt-5")
            response = client.responses.create(
                model=model,
                instructions=SYSTEM_PROMPT,
                input=self.messages[-20:]
            )
            self.finished_reply.emit(response.output_text)
        except Exception as exc:
            self.failed.emit(str(exc))

class ReminderToast(QWidget):
    dismissed = Signal()

    def __init__(self, title, message):
        super().__init__(None)
        self.setWindowTitle("Mommy reminder")
        self.setWindowFlags(
            Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(360, 145)
        layout = QVBoxLayout(self)
        heading = QLabel("♡  MOMMY'S LITTLE REMINDER")
        heading.setStyleSheet("color:#f3a8ce;font-size:14px;font-weight:800;")
        body = QLabel(f"<b>{title}</b><br>{message}")
        body.setWordWrap(True)
        body.setStyleSheet("color:#fff0f7;font-size:13px;")
        close = QPushButton("Okay, I'll do it ♡")
        close.clicked.connect(self.close_toast)
        layout.addWidget(heading)
        layout.addWidget(body, 1)
        layout.addWidget(close)
        self.setStyleSheet("""
            QWidget { background:#241d28; border:1px solid #d982b1; border-radius:14px; }
            QPushButton { background:#d982b1; color:#21131c; border:0;
                          border-radius:8px; padding:8px; font-weight:700; }
        """)

    def showEvent(self, event):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.right() - self.width() - 24, screen.bottom() - self.height() - 24)
        super().showEvent(event)

    def close_toast(self):
        self.dismissed.emit()
        self.close()

class MommyWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = load_data()
        self.history = []
        self.worker = None
        self.toast = None
        self.pending_reminders = []
        self.shown_today = set()
        self.last_fullscreen = False

        self.setWindowTitle("Mommy Desktop Assistant ♡")
        self.resize(1120, 760)
        self.setMinimumSize(900, 650)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QVBoxLayout(root)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(12)

        header = QHBoxLayout()
        title = QLabel("♡  MOMMY DESKTOP ASSISTANT")
        title.setObjectName("title")
        header.addWidget(title)
        header.addStretch()
        self.clock = QLabel()
        self.clock.setObjectName("clock")
        header.addWidget(self.clock)
        outer.addLayout(header)

        main = QHBoxLayout()
        main.setSpacing(14)
        outer.addLayout(main, 1)

        left = QVBoxLayout()
        main.addLayout(left, 5)
        art_frame = QFrame()
        art_frame.setObjectName("artFrame")
        art_layout = QVBoxLayout(art_frame)
        self.art = QLabel()
        self.art.setAlignment(Qt.AlignCenter)
        pix = QPixmap(str(ROOT / "assets" / "mommy_character.jpg"))
        if not pix.isNull():
            self.art.setPixmap(pix.scaled(560, 470, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.art.setText("Put mommy_character.jpg inside the assets folder.")
        art_layout.addWidget(self.art)
        left.addWidget(art_frame, 1)

        self.status = QLabel("● Online · Ready to help")
        self.status.setObjectName("status")
        left.addWidget(self.status)

        right = QVBoxLayout()
        main.addLayout(right, 5)

        calendar_frame = QFrame()
        calendar_frame.setObjectName("panel")
        cal_layout = QVBoxLayout(calendar_frame)
        cal_title = QLabel("📅  Calendar")
        cal_title.setObjectName("sectionTitle")
        cal_layout.addWidget(cal_title)
        self.calendar = QCalendarWidget()
        self.calendar.setGridVisible(True)
        self.calendar.selectionChanged.connect(self.update_selected_date)
        cal_layout.addWidget(self.calendar)
        right.addWidget(calendar_frame)

        tasks_frame = QFrame()
        tasks_frame.setObjectName("panel")
        task_layout = QVBoxLayout(tasks_frame)
        task_head = QHBoxLayout()
        task_title = QLabel("🔔  Work reminders")
        task_title.setObjectName("sectionTitle")
        task_head.addWidget(task_title)
        task_head.addStretch()
        add_task = QPushButton("+ Add")
        add_task.clicked.connect(self.add_task)
        task_head.addWidget(add_task)
        task_layout.addLayout(task_head)
        self.task_list = QListWidget()
        self.task_list.setMaximumHeight(145)
        task_layout.addWidget(self.task_list)
        task_actions = QHBoxLayout()
        remove_task = QPushButton("Remove selected")
        remove_task.clicked.connect(self.remove_task)
        task_actions.addWidget(remove_task)
        task_layout.addLayout(task_actions)
        right.addWidget(tasks_frame)

        chat_frame = QFrame()
        chat_frame.setObjectName("panel")
        chat_layout = QVBoxLayout(chat_frame)
        chat_title = QLabel("💬  Chat with mommy")
        chat_title.setObjectName("sectionTitle")
        chat_layout.addWidget(chat_title)
        self.chat = QTextEdit()
        self.chat.setReadOnly(True)
        self.chat.setMaximumHeight(145)
        self.chat.append("Mommy: Hmph! You're back. Let's make today a good one~ ♡")
        chat_layout.addWidget(self.chat)
        row = QHBoxLayout()
        self.entry = QLineEdit()
        self.entry.setPlaceholderText("Ask me something...")
        self.entry.returnPressed.connect(self.send_message)
        row.addWidget(self.entry, 1)
        send = QPushButton("Send ♡")
        send.clicked.connect(self.send_message)
        row.addWidget(send)
        chat_layout.addLayout(row)
        right.addWidget(chat_frame, 1)

        settings = QHBoxLayout()
        self.fullscreen_check = QCheckBox("Allow reminders over fullscreen games/apps")
        self.fullscreen_check.setChecked(self.data["settings"].get("show_over_fullscreen", False))
        self.fullscreen_check.toggled.connect(self.save_settings)
        settings.addWidget(self.fullscreen_check)
        self.startup_check = QCheckBox("Start with Windows")
        self.startup_check.setChecked(self.data["settings"].get("start_with_windows", False))
        self.startup_check.toggled.connect(self.toggle_startup)
        settings.addWidget(self.startup_check)
        settings.addStretch()
        outer.addLayout(settings)

        self.setStyleSheet("""
            QWidget#root { background:#17141b; color:#f8eaf2; }
            QLabel#title { color:#f3a8ce; font-size:19px; font-weight:800; }
            QLabel#clock { color:#f6c6df; font-size:17px; font-weight:700; }
            QLabel#status { color:#a9e6b4; padding:4px; }
            QFrame#artFrame, QFrame#panel { background:#241d28; border:1px solid #76506b; border-radius:14px; }
            QLabel#sectionTitle { color:#f5b4d5; font-size:15px; font-weight:700; }
            QTextEdit, QLineEdit, QListWidget, QCalendarWidget QWidget {
                background:#17131a; color:#fff0f7; border:1px solid #76506b; border-radius:7px; padding:5px;
            }
            QPushButton { background:#d982b1; color:#21131c; border:0; border-radius:8px;
                          padding:8px 12px; font-weight:700; }
            QPushButton:hover { background:#efa5ca; }
            QCheckBox { color:#e9d9e3; spacing:6px; }
        """)

        self.tray = None
        self.setup_tray()
        self.refresh_tasks()
        self.update_clock()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(1000)

    def setup_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        self.tray = QSystemTrayIcon(self)
        self.tray.setToolTip("Mommy Desktop Assistant")
        menu = QMenu()
        show_action = QAction("Open mommy", self)
        show_action.triggered.connect(self.show_normal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(QApplication.quit)
        menu.addAction(show_action)
        menu.addSeparator()
        menu.addAction(quit_action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.show_normal())
        self.tray.show()

    def show_normal(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def update_clock(self):
        now = datetime.now()
        self.clock.setText(now.strftime("%A, %d %B  ·  %I:%M:%S %p"))

    def update_selected_date(self):
        self.refresh_tasks()

    def refresh_tasks(self):
        self.task_list.clear()
        selected = self.calendar.selectedDate().toPython()
        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        for task in self.data["tasks"]:
            days = task.get("days", list(range(7)))
            active = selected.weekday() in days
            mark = "✓" if task.get("enabled", False) and active else "○"
            item = QListWidgetItem(f"{mark}  {task.get('time','--:--')}  {task.get('title','Task')}")
            item.setData(Qt.UserRole, task.get("id"))
            if not active:
                item.setForeground(Qt.gray)
            self.task_list.addItem(item)

    def add_task(self):
        title, ok = QInputDialog.getText(self, "New reminder", "What should mommy remind you about?")
        if not ok or not title.strip():
            return
        from PySide6.QtWidgets import QTimeEdit, QDialog, QDialogButtonBox, QFormLayout
        dialog = QDialog(self)
        dialog.setWindowTitle("Reminder time")
        form = QFormLayout(dialog)
        time_edit = QTimeEdit()
        time_edit.setDisplayFormat("HH:mm")
        time_edit.setTime(datetime.now().replace(hour=20, minute=0).time())
        form.addRow("Time:", time_edit)
        message_edit = QLineEdit("Hmph! It's time to focus, good boy~ ♡")
        form.addRow("Mommy's message:", message_edit)
        enabled = QCheckBox("Enable this reminder")
        enabled.setChecked(True)
        form.addRow(enabled)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.Accepted:
            return
        self.data["tasks"].append({
            "id": str(datetime.now().timestamp()),
            "title": title.strip(),
            "time": time_edit.time().toString("HH:mm"),
            "days": list(range(7)),
            "message": message_edit.text().strip(),
            "enabled": enabled.isChecked()
        })
        save_data(self.data)
        self.refresh_tasks()

    def remove_task(self):
        item = self.task_list.currentItem()
        if not item:
            return
        task_id = item.data(Qt.UserRole)
        self.data["tasks"] = [t for t in self.data["tasks"] if t.get("id") != task_id]
        save_data(self.data)
        self.refresh_tasks()

    def save_settings(self):
        self.data["settings"]["show_over_fullscreen"] = self.fullscreen_check.isChecked()
        save_data(self.data)

    def toggle_startup(self, enabled):
        self.data["settings"]["start_with_windows"] = enabled
        save_data(self.data)
        if sys.platform != "win32":
            QMessageBox.information(self, "Startup", "Automatic startup setup is supported on Windows only.")
            self.startup_check.setChecked(False)
            return
        try:
            startup = Path(os.getenv("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs/Startup"
            startup.mkdir(parents=True, exist_ok=True)
            link = startup / "Mommy Desktop Assistant.bat"
            if enabled:
                pythonw = Path(sys.executable).with_name("pythonw.exe")
                python_exe = pythonw if pythonw.exists() else Path(sys.executable)
                link.write_text(f'@echo off\ncd /d "{ROOT}"\nstart "" "{python_exe}" "{ROOT / "main.py"}"\n', encoding="utf-8")
            elif link.exists():
                link.unlink()
            self.status.setText("● Startup setting updated")
        except Exception as exc:
            self.startup_check.blockSignals(True)
            self.startup_check.setChecked(False)
            self.startup_check.blockSignals(False)
            self.data["settings"]["start_with_windows"] = False
            save_data(self.data)
            QMessageBox.warning(self, "Startup setup", str(exc))

    def tick(self):
        self.update_clock()
        now = datetime.now()
        key = now.strftime("%Y-%m-%d %H:%M")
        fullscreen = is_windows_fullscreen()
        if self.last_fullscreen and not fullscreen and self.pending_reminders:
            title, message = self.pending_reminders.pop(0)
            self.show_reminder(title, message, force=True)
        self.last_fullscreen = fullscreen

        for task in self.data["tasks"]:
            if not task.get("enabled", False):
                continue
            if now.weekday() not in task.get("days", list(range(7))):
                continue
            if now.strftime("%H:%M") != task.get("time"):
                continue
            task_key = f"{task.get('id')}:{key}"
            if task_key in self.shown_today:
                continue
            self.shown_today.add(task_key)
            self.show_reminder(task.get("title", "Work time"), task.get("message", "Time to focus~ ♡"))

    def show_reminder(self, title, message, force=False):
        fullscreen = is_windows_fullscreen()
        allow = self.data["settings"].get("show_over_fullscreen", False)
        if fullscreen and not allow and not force:
            self.pending_reminders.append((title, message))
            self.status.setText("● Reminder waiting until fullscreen ends")
            if self.tray:
                self.tray.showMessage("Mommy has a reminder ♡", "I'll wait until you're out of fullscreen.")
            return
        if self.toast:
            self.toast.close()
        self.toast = ReminderToast(title, message)
        self.toast.show()
        if self.tray:
            self.tray.showMessage(title, message)

    def send_message(self):
        message = self.entry.text().strip()
        if not message or (self.worker and self.worker.isRunning()):
            return
        self.entry.clear()
        self.chat.append(f"You: {message}")
        self.history.append({"role": "user", "content": message})
        self.status.setText("● Thinking...")
        self.worker = ReplyWorker(self.history)
        self.worker.finished_reply.connect(self.on_reply)
        self.worker.failed.connect(self.on_error)
        self.worker.start()

    def on_reply(self, reply):
        self.chat.append(f"Mommy: {reply}")
        self.history.append({"role": "assistant", "content": reply})
        self.status.setText("● Online · Ready to help")

    def on_error(self, error):
        self.chat.append(f"App: {error}")
        self.status.setText("● Check API setup")

    def closeEvent(self, event):
        if self.tray:
            self.hide()
            event.ignore()
        else:
            event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    window = MommyWindow()
    window.show()
    sys.exit(app.exec())

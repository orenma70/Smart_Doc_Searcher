import sys
import speech_recognition as sr
from PyQt5.QtCore import QThread, pyqtSignal, QObject, Qt
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QLabel, QComboBox, QDialog, QRadioButton, QButtonGroup)

class VoiceWorker(QObject):
    text_received = pyqtSignal(str)
    status_signal = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, language="he-IL"):
        super().__init__()
        self.language = language
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.stop_listening = None  # For manual mode

    # --- MODE 1: AUTOMATIC (LISTEN) ---
    def run_automatic(self):
        with self.microphone as source:
            self.status_signal.emit("Listening (Auto-stop on silence)...")
            try:
                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=10)
                self.process_audio(audio)
            except Exception as e:
                self.text_received.emit(f"Error: {str(e)}")
            finally:
                self.finished.emit()

    # --- MODE 2: MANUAL ---
    def start_manual(self):
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
        self.status_signal.emit("Recording (Manual mode)...")
        # Starts background thread
        self.stop_listening = self.recognizer.listen_in_background(self.microphone, self.manual_callback)

    def manual_callback(self, recognizer, audio):
        self.process_audio(audio)
        self.finished.emit()

    def stop_manual(self):
        if self.stop_listening:
            self.stop_listening(wait_for_stop=False)

    def process_audio(self, audio):
        try:
            text = self.recognizer.recognize_google(audio, language=self.language)
            self.text_received.emit(text)
        except Exception as e:
            self.text_received.emit(f"Speech not recognized: {str(e)}")


class StopDialog(QDialog):
    def __init__(self, parent=None, language="he-IL"):
        super().__init__(parent)
        self.setWindowTitle("Voice Recording")
        self.setMinimumSize(400, 250)

        # 1. Initialize Worker inside the Dialog
        self.worker = VoiceWorker(language=language)
        self.final_text = ""

        # UI Setup
        layout = QVBoxLayout(self)
        self.label = QLabel("🔴 Recording... Speak now.")
        self.label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.label)

        self.stop_btn = QPushButton("STOP RECORDING")
        self.stop_btn.setFixedHeight(60)
        self.stop_btn.clicked.connect(self.process_and_close)
        layout.addWidget(self.stop_btn)

        # 2. Start recording immediately
        self.worker.start_manual()

    def process_and_close(self):
        self.label.setText("⌛ Processing speech... please wait.")
        self.stop_btn.setEnabled(False)

        # Connect signal to the result handler
        self.worker.text_received.connect(self.handle_result)
        # Tell worker to stop and send to Google
        self.worker.stop_manual()

    def handle_result(self, text):
        self.final_text = text
        self.accept()  # This releases the .exec_() lock

    @staticmethod
    def get_voice_text(parent=None, language="he-IL"):
        """This matches your GCS Browser style"""
        dialog = StopDialog(parent=parent, language=language)
        if dialog.exec_() == QDialog.Accepted:
            return dialog.final_text
        return ""

class VoiceRecorderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # Language Selection
        top_row = QHBoxLayout()
        top_row.addWidget(QLabel("Language:"))
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Hebrew", "he-IL")
        self.lang_combo.addItem("English", "en-US")
        top_row.addWidget(self.lang_combo)
        layout.addLayout(top_row)

        # Radio Buttons for Mode
        mode_layout = QHBoxLayout()
        self.radio_listen = QRadioButton("Listen (Auto)")
        self.radio_manual = QRadioButton("Manual (Stop Button)")
        self.radio_listen.setChecked(True)

        self.mode_group = QButtonGroup()
        self.mode_group.addButton(self.radio_listen)
        self.mode_group.addButton(self.radio_manual)

        mode_layout.addWidget(self.radio_listen)
        mode_layout.addWidget(self.radio_manual)
        layout.addLayout(mode_layout)

        # Status and Text Area
        self.status_label = QLabel("Select mode and press Start")
        layout.addWidget(self.status_label)
        self.text_display = QTextEdit()
        layout.addWidget(self.text_display)

        self.start_btn = QPushButton("🎤")
        self.start_btn.setFixedHeight(60)
        self.start_btn.setFixedWidth(60)
        self.start_btn.clicked.connect(self.handle_recording)
        layout.addWidget(self.start_btn)

        self.setLayout(layout)
        self.setWindowTitle("Walla/Outlook Voice Input")
        self.resize(450, 400)

    def handle_recording(self):
        self.text_display.clear()
        lang = self.lang_combo.currentData()
        self.worker = VoiceWorker(language=lang)
        self.worker.text_received.connect(self.text_display.setText)
        self.worker.status_signal.connect(self.status_label.setText)

        if self.radio_listen.isChecked():
            # Auto Mode logic
            self.thread = QThread()
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run_automatic)
            self.worker.finished.connect(self.thread.quit)
            self.start_btn.setEnabled(False)
            self.thread.finished.connect(lambda: self.start_btn.setEnabled(True))
            self.thread.start()
        else:
            # Manual Mode logic
            self.worker.start_manual()
            dialog = StopDialog(self)
            if dialog.exec_() == QDialog.Accepted:
                self.status_label.setText("Processing...")
                self.worker.stop_manual()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VoiceRecorderApp()
    window.show()
    sys.exit(app.exec_())
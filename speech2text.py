import sys, time
import speech_recognition as sr
from PyQt5.QtCore import QThread, pyqtSignal, QObject, Qt, QTimer
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
                             QTextEdit, QLabel, QComboBox, QDialog, QRadioButton, QButtonGroup)


class VoiceWorker(QObject):
    text_received = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, language="he-IL", mode = "auto"):
        super().__init__()
        self.language = language
        self.mode = mode
        self.recognizer = sr.Recognizer()
        self.microphone = sr.Microphone()
        self.stop_listening = None
        self._has_processed = False

    def run_automatic(self):
        with self.microphone as source:
            try:
                # How long to wait for the user to start speaking
                self.recognizer.pause_threshold = 1  # Increase this if words are cut off (default is 0.8)

                # This is crucial: it prevents cutting off the last word if you pause slightly
                self.recognizer.phrase_threshold = 0.3

                # This handles the silence at the end
                self.recognizer.non_speaking_duration = 1

                self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = self.recognizer.listen(source, timeout=10)
                self.process_audio(audio)
            except Exception:
                self.finished.emit()

    def start_manual(self):
        self._has_processed = False
        with self.microphone as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
        self.stop_listening = self.recognizer.listen_in_background(self.microphone, self.manual_callback)

    def manual_callback(self, recognizer, audio):
        self._has_processed = True
        self.process_audio(audio)

    def stop_manual(self):
        if self.stop_listening:
            self.stop_listening(wait_for_stop=False)
            self.stop_listening = None
            QTimer.singleShot(1000, self._force_finish_if_stuck)


    def _force_finish_if_stuck(self):
        if not self._has_processed:
            self.finished.emit()

    def process_audio(self, audio):
        try:
            text = self.recognizer.recognize_google(audio, language=self.language)
            self.text_received.emit(text)
        except Exception:
            self.text_received.emit("")
        finally:
            self.finished.emit()


class StopDialog(QDialog):
    def __init__(self, parent=None, language="he-IL", external=False, mode = "auto"):
        super().__init__(parent)
        self.language = language
        self.mode = mode
        self.final_text = ""
        self.external = external  # Flag to know if we are being called from outside

        self.setWindowTitle("Voice Input Active")
        self.setMinimumSize(400, 250)
        self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        layout = QVBoxLayout(self)
        self.label = QLabel("🔴 Recording...")
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setStyleSheet("font-size: 22px; font-weight: bold; color: #d32f2f;")
        layout.addWidget(self.label)

        self.stop_btn = QPushButton("STOP RECORDING")
        self.stop_btn.setFixedHeight(80)
        self.stop_btn.setStyleSheet(
            "background-color: #ff4d4d; color: white; font-size: 18px; font-weight: bold; border-radius: 10px;")
        layout.addWidget(self.stop_btn)

        if self.external:
            # Called from get_voice_text: Dialog handles its own worker
            self.stop_btn.clicked.connect(self.process_and_wait)
            self.worker = VoiceWorker(language=self.language, mode = self.mode)
            self.worker.text_received.connect(self.handle_result)
            self.worker.start_manual()
        else:
            # Standalone mode: Just behave as a simple close button
            self.stop_btn.clicked.connect(self.accept)

    def process_and_wait(self):
        self.label.setText("⌛ Processing speech... please wait.")
        self.stop_btn.setEnabled(False)
        self.worker.stop_manual()

    def handle_result(self, text):
        self.final_text = text
        self.accept()

    @staticmethod
    def get_voice_text(parent=None, language="he-IL", mode = "auto"):
        dialog = StopDialog(parent=parent, language=language, external=True, mode = mode)
        if dialog.exec_() == QDialog.Accepted:
            return dialog.final_text
        return ""


class VoiceRecorderApp(QWidget):
    def __init__(self):
        super().__init__()
        self.initUI()
        self.worker = None
        self.thread = None

    def initUI(self):
        layout = QVBoxLayout(self)
        self.lang_combo = QComboBox()
        self.lang_combo.addItem("Hebrew", "he-IL")
        self.lang_combo.addItem("English", "en-US")
        layout.addWidget(self.lang_combo)

        self.radio_listen = QRadioButton("Listen (Auto)")
        self.radio_manual = QRadioButton("Manual (Stop Button)")
        self.radio_manual.setChecked(True)
        layout.addWidget(self.radio_listen)
        layout.addWidget(self.radio_manual)

        self.status_label = QLabel("Ready")
        layout.addWidget(self.status_label)
        self.text_display = QTextEdit()
        layout.addWidget(self.text_display)

        self.start_btn = QPushButton("🎤")
        self.start_btn.setFixedHeight(60)


        self.start_btn.clicked.connect(self.get_text)
        layout.addWidget(self.start_btn)

    def get_text(self, lang ="", mode_in = "auto"):
        if __name__ == '__main__':
            lang = self.lang_combo.currentData()
            if self.radio_listen.isChecked():
                mode = "auto"
            else:
                mode = "manual"

        else:
            mode = mode_in
            lang = lang

        self.handle_recording(lang, mode)

    def handle_recording(self, lang , mode = "auto"):
        self.text_display.clear()
        self.start_btn.setEnabled(False)
        self.status_label.setText("Recording...")

        self.worker = VoiceWorker(language=lang)
        self.worker.text_received.connect(self.text_display.setText, Qt.QueuedConnection)
        self.worker.finished.connect(self.on_finished, Qt.QueuedConnection)

        if mode == "auto":
            self.thread = QThread()
            self.worker.moveToThread(self.thread)
            self.thread.started.connect(self.worker.run_automatic)

            self.auto_dialog = StopDialog(self, language=lang, external=False)
            self.auto_dialog.label.setText("🎙️ Please ask your question...")
            self.auto_dialog.stop_btn.setText("CANCEL")

            # Close the dialog automatically when the worker finishes
            self.worker.finished.connect(self.auto_dialog.accept)




            self.thread.start()
            self.auto_dialog.show()  # .show() is non-blocking






        else:
            self.worker.start_manual()
            # external=False means the worker is owned by VoiceRecorderApp
            dialog = StopDialog(self, language=lang, external=False)
            dialog.exec_()
            self.status_label.setText("Processing...")
            self.worker.stop_manual()

    def on_finished(self):
        self.status_label.setText("Done")
        self.start_btn.setEnabled(True)
        if self.thread:
            self.thread.quit()
            self.thread.wait()
            self.thread = None


if __name__ == '__main__':
    app = QApplication(sys.argv)
    window = VoiceRecorderApp()
    window.show()
    sys.exit(app.exec_())
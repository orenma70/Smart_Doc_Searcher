from PyQt5 import QtWidgets, QtCore, QtGui
from google.genai import types
from config_reader import LOCAL_MODE, CLIENT_PREFIX_TO_STRIP
from utils import (CHECKBOX_STYLE_QSS_black, CHECKBOX_STYLE_QSS_gray, CHECKBOX_STYLE_QSS_blue, CHECKBOX_STYLE_QSS_red,
                   Container_STYLE_QSS, Radio_STYLE_QSS_green, Radio_STYLE_QSS_red, QRadioButton_STYLE_QSS_green_1515bg,QRadioButton_STYLE_QSS_green_1616bg,
                   QRadioButton_STYLE_QSS_green_1520bg)
Vertic_Flag = True
isLTR = False # left to right or RTL
chat_mode = True


if isLTR:

    non_cloud_str = " 🖴 HD"

    non_sync_cloud_str = "☁️ Cloud non synchronized ❌"
    sync_cloud_str = "☁️  Cloud synchronized 🔄"


    btn_browse_str = "Choose Search Folder"
    tik_str = "Folder --->"
    dir_edit_alignment_choice = QtCore.Qt.AlignmentFlag.AlignLeft
    dir_edit_LayoutDirection = QtCore.Qt.LayoutDirection.LeftToRight
    search_btn_str = " Start Search !!"
    label_str = " Enter Search Words -->"
    label_gpt_str = " Ask your question -->"
    #search_input_words_str = "Enter here search words"
    setText_str = "default message here"
    clear_btn_str = "Clear ?"

    nongemini_radio_str = " Keyword Matching"  # Semantic Search "
    gemini_radio_str = " Ask Chat "

    exact_search_radio_str = " Match full word "
    partial_search_radio_str = " Match partially "
    all_word_search_radio_str = " All Words "
    any_word_search_radio_str = " One word "

    save_btn_str = "Save 💾"

    paragraph_str = " Show in paragraphs "
    line_str = " Show in line "
else:
    non_sync_cloud_str = "☁️ ענן לא מסונכרן ❌"
    sync_cloud_str = "☁️ ענן מסונכרן 🔄"
    non_cloud_str = " 🖴 כונן"

    btn_browse_str = "בחירת תיקיית 📂 חיפוש"
    tik_str = "  📂 תיקיה--->"
    dir_edit_alignment_choice = QtCore.Qt.AlignmentFlag.AlignRight
    dir_edit_LayoutDirection = QtCore.Qt.LayoutDirection.RightToLeft





    search_btn_str = "! לחצן החיפוש !"
    label_str = "  הכנסת מילות חיפוש ✏️-->"
    label_gpt_str = " הכנסת השאלה ✏️-->"
    #search_input_words_str = "Enter here search words"
    search_input_question_str = "הכנסת השאלה"
    setText_str =  "ללימודי"  #  "מי היא חברת הליסינג?"     "מה גיל הילדים?"    "מי האקטואר?
    clear_btn_str = " ניקוי 🗑️ "

    nongemini_radio_str = "  חיפוש מילים  "
    gemini_radio_str = " שאל את הצ'אט "

    exact_search_radio_str = " התאמה מלאה "
    partial_search_radio_str = " התאמה חלקית "
    all_word_search_radio_str = " כל המילים "
    any_word_search_radio_str  = " חיפוש אחת המילים"

    paragraph_str = " הצגת כל הפסקה "
    line_str = " הצגת שורה "

    save_btn_str = "שמירה 💾"

def setup_ui(self):
    font = QtGui.QFont()
    font.setPointSize(16)
    font2 = QtGui.QFont()
    font2.setPointSize(24)
    layout = QtWidgets.QVBoxLayout(self)


    # Directory input row
    dir_layout = QtWidgets.QHBoxLayout()
    self.dir_edit = QtWidgets.QLineEdit()
    self.dir_edit.setFont(font)
    self.dir_edit.setAlignment(dir_edit_alignment_choice)
    self.dir_edit.setLayoutDirection(dir_edit_LayoutDirection)




    self.load_last_dir()

    btn_browse = QtWidgets.QPushButton(btn_browse_str )
    btn_browse.setStyleSheet("""
        QPushButton {
            background-color: black; 
            color: white;
            border: 6px solid #0000ff;
            border-radius: 4px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #0069d9;
            border-color: #0056b3;
        }
    """)
    btn_browse.setFont(font)
    btn_browse.clicked.connect(self.browse_directory)

    tik = QtWidgets.QLabel(tik_str)
    tik.setFont(font)

    search_layout = QtWidgets.QHBoxLayout()
    self.save_btn = QtWidgets.QPushButton(save_btn_str)
    self.save_btn.setStyleSheet("""
                QPushButton {
                    background-color: black;
                    color: white;
                    border: 6px solid #ff0000;
                    border-radius: 4px;
                    padding: 6px 12px;
                }
                QPushButton:hover {
                    background-color: #0069d9;
                    border-color: #ff0000;
                }
            """)
    self.save_btn.setFont(font)
    self.save_btn.clicked.connect(self.save_all2file)

    self.clear_btn = QtWidgets.QPushButton(clear_btn_str)
    self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: black;
                color: white;
                border: 6px solid #ff0000;
                border-radius: 4px;
                padding: 6px 12px;
            }
            QPushButton:hover {
                background-color: #0069d9;
                border-color: #ff0000;
            }
        """)
    self.clear_btn.setFont(font)
    self.clear_btn.clicked.connect(self.clear_all)

    if LOCAL_MODE == "True":
        self.display_root = QtWidgets.QLabel(CLIENT_PREFIX_TO_STRIP)
    else:
        self.display_root = QtWidgets.QLabel("☁️ Bucket")
        self.display_root.setStyleSheet("color: red;")

    self.display_root.setFont(font)


    if isLTR:
        dir_layout.addWidget(btn_browse)
        dir_layout.addWidget(tik)
        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(self.display_root)
        dir_layout.addSpacing(200)
        dir_layout.addWidget(self.clear_btn)
        dir_layout.addWidget(self.save_btn)
    else:
        dir_layout.addWidget(self.save_btn)
        dir_layout.addWidget(self.clear_btn)
        dir_layout.addSpacing(200)
        dir_layout.addWidget(self.display_root)
        dir_layout.addWidget(self.dir_edit)
        dir_layout.addWidget(tik)
        dir_layout.addWidget(btn_browse)

    layout.addLayout(dir_layout)

    # Search query input

    self.search_input = QtWidgets.QLineEdit()
    self.search_input.setFont(font)

    self.search_input.setText(setText_str)
    self.search_btn = QtWidgets.QPushButton(search_btn_str)


    self.search_btn.setStyleSheet("""
        QPushButton {
            background-color: black;
            color: white;
            border: 6px solid #0000ff;
            border-radius: 4px;
            padding: 6px 12px;
        }
        QPushButton:hover {
            background-color: #0069d9;
            border-color: #0056b3;
        }
    """)
    self.search_btn.setFont(font)
    self.search_btn.clicked.connect(self.execute_search)

    self.label = QtWidgets.QLabel(label_str)
    self.label.setFont(font)


    self.cloud_gemini_radio = QtWidgets.QCheckBox(non_sync_cloud_str)




    self.non_cloud_gemini_radio = QtWidgets.QCheckBox(non_cloud_str)


    #self.non_cloud_gemini_radio.toggled.connect(self.handle_radio_check)


    self.mode_group_cloud = QtWidgets.QButtonGroup()
    self.mode_group_cloud.addButton(self.cloud_gemini_radio)
    self.mode_group_cloud.addButton(self.non_cloud_gemini_radio)


    if LOCAL_MODE == "True":
        self.non_cloud_gemini_radio.setChecked(True)
        self.non_cloud_gemini_radio.setStyleSheet(CHECKBOX_STYLE_QSS_black)
        self.cloud_gemini_radio.setStyleSheet(CHECKBOX_STYLE_QSS_gray)
    else:
        self.cloud_gemini_radio.setChecked(True)
        self.cloud_gemini_radio.setStyleSheet(CHECKBOX_STYLE_QSS_black)
        self.non_cloud_gemini_radio.setStyleSheet(CHECKBOX_STYLE_QSS_gray)

    self.cloud_gemini_radio.toggled.connect(self.handle_radio_check)

    if isLTR:
        search_layout.addWidget(self.save_btn)
        search_layout.addWidget(self.label)
        search_layout.addWidget(self.search_input)
        search_layout.addSpacing(100)
        search_layout.addWidget(self.non_cloud_gemini_radio)
        search_layout.addWidget(self.cloud_gemini_radio)
    else:
        search_layout.addWidget(self.cloud_gemini_radio)
        search_layout.addWidget(self.non_cloud_gemini_radio)
        search_layout.addSpacing(100)
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.label)
        search_layout.addWidget(self.search_btn)

    layout.addLayout(search_layout)
    self.nongemini_radio = QtWidgets.QRadioButton(nongemini_radio_str)
    #if not chat_mode:
    #self.nongemini_radio.setChecked(True)


    if  not chat_mode:
        self.search_input.setPlaceholderText(label_str)
        self.nongemini_radio.setStyleSheet(QRadioButton_STYLE_QSS_green_1520bg)
    else:
        self.search_input.setPlaceholderText(label_gpt_str)


    self.nongemini_radio.setFont(font2)



    # Radio buttons for search mode (search words / gemini)
    self.gemini_radio = QtWidgets.QRadioButton(gemini_radio_str)
    if  chat_mode:
        self.gemini_radio.setChecked(True)
        self.gemini_radio.setStyleSheet(QRadioButton_STYLE_QSS_green_1616bg)

        self.nongemini_radio.setStyleSheet(QRadioButton_STYLE_QSS_green_1515bg)


    self.gemini_radio.setFont(font2)

    # In your setup_ui, after creating the radio button:
    self.gemini_radio.toggled.connect(self.update_search_button_text)



    # Create your search mode radio buttons for quick search options
    self.partial_search_radio = QtWidgets.QRadioButton(partial_search_radio_str)
    self.partial_search_radio.setChecked(True)
    self.partial_search_radio.setFont(font)
    self.partial_search_radio.setStyleSheet("""
        QRadioButton::indicator {
            width: 15px;
            height: 15px;
            border-radius: 6px;
            border: 6px solid black;
        }
        QRadioButton::indicator:checked {
            background-color: blue;
        }
    """)



    self.exact_search_radio = QtWidgets.QRadioButton(exact_search_radio_str)
    self.exact_search_radio.setFont(font)
    self.exact_search_radio.setStyleSheet("""
        QRadioButton::indicator {
            width: 15px;
            height: 15px;
            border-radius: 6px;
            border: 6px solid black;
        }
        QRadioButton::indicator:checked {
            background-color: blue;
        }
    """)

    self.all_word_search_radio = QtWidgets.QRadioButton(all_word_search_radio_str)
    self.all_word_search_radio.setChecked(True)
    self.all_word_search_radio.setFont(font)
    self.all_word_search_radio.setStyleSheet(Radio_STYLE_QSS_red)

    self.any_word_search_radio = QtWidgets.QRadioButton(any_word_search_radio_str)
    self.any_word_search_radio.setFont(font)
    self.any_word_search_radio.setStyleSheet(Radio_STYLE_QSS_red)

    self.show_line_mode_radio = QtWidgets.QRadioButton(line_str)
    self.show_line_mode_radio.setFont(font)
    self.show_line_mode_radio.setStyleSheet(Radio_STYLE_QSS_green)

    self.show_paragraph_mode_radio = QtWidgets.QRadioButton(paragraph_str)
    self.show_paragraph_mode_radio.setFont(font)
    self.show_paragraph_mode_radio.setChecked(True)
    self.show_paragraph_mode_radio.setStyleSheet(Radio_STYLE_QSS_green)
    # --- Create two button groups for mutual exclusivity
    self.mode_group1 = QtWidgets.QButtonGroup()
    self.mode_group2 = QtWidgets.QButtonGroup()
    self.mode_group3 = QtWidgets.QButtonGroup()
    self.mode_group4 = QtWidgets.QButtonGroup()

    # Add buttons to respective groups
    self.mode_group1.addButton(self.gemini_radio)
    self.mode_group1.addButton(self.nongemini_radio)

    self.mode_group2.addButton(self.partial_search_radio)
    self.mode_group2.addButton(self.exact_search_radio)

    self.mode_group3.addButton(self.all_word_search_radio)
    self.mode_group3.addButton(self.any_word_search_radio)

    self.mode_group4.addButton(self.show_paragraph_mode_radio)
    self.mode_group4.addButton(self.show_line_mode_radio)

    # Layout for the two groups of radio buttons
    # First group (gemini / Search Words)
    #g1_layout = QtWidgets.QHBoxLayout()

    g2_container = QtWidgets.QWidget()
    g2_layout = QtWidgets.QHBoxLayout(g2_container)
    #g2_layout.addWidget(self.clear_btn)

    g3_container = QtWidgets.QWidget()

    if Vertic_Flag:
        g3_layout = QtWidgets.QVBoxLayout(g3_container)
    else:
        g3_layout = QtWidgets.QHBoxLayout(g3_container)

    g3_layout.addWidget(self.nongemini_radio)
    g3_layout.addWidget(self.gemini_radio)
    g3_layout.addStretch()

    g3_container.setStyleSheet(Container_STYLE_QSS)
    small_gap = 10
    g11_container = QtWidgets.QWidget()
    g11_layout = QtWidgets.QHBoxLayout(g11_container)

    g11_layout.addWidget(self.all_word_search_radio)
    g11_layout.addSpacing(small_gap)
    g11_layout.addWidget(self.any_word_search_radio)
    g11_layout.addStretch()

    g11_container.setStyleSheet(Container_STYLE_QSS)

    g12_container = QtWidgets.QWidget()
    g12_layout = QtWidgets.QHBoxLayout(g12_container)
    g12_layout.addWidget(self.show_paragraph_mode_radio)
    g12_layout.addSpacing(small_gap)
    g12_layout.addWidget(self.show_line_mode_radio)
    g12_layout.addStretch()

    g12_container.setStyleSheet(Container_STYLE_QSS)
    both_groups_layout = QtWidgets.QHBoxLayout()

    # Second group (Partial / Exact)
    #g2_layout = QtWidgets.QHBoxLayout()

    g1_container = QtWidgets.QWidget()
    g1_container.setStyleSheet(Container_STYLE_QSS)
    g1_layout = QtWidgets.QHBoxLayout(g1_container)
    g1_layout.addWidget(self.partial_search_radio)
    g1_layout.addSpacing(small_gap)
    g1_layout.addWidget(self.exact_search_radio)



    self.g_group_widget = QtWidgets.QWidget()
    self.g_group_widget.setStyleSheet("""
        background-color: #0000FF;
        border: 2px solid #000000;
        border-radius: 6px;
        padding: 8px;
    """)



    self.e_group_widget = QtWidgets.QWidget()
    self.e_group_widget.setStyleSheet("""
            background-color: #00F000;
            border: 2px solid #000000;
            border-radius: 6px;
            padding: 8px;
        """)

    gap12 = 30

    if Vertic_Flag:
        g_group_layout = QtWidgets.QVBoxLayout(self.g_group_widget)
        g_group_layout.addWidget(g11_container)
        g_group_layout.addWidget(g1_container)
        g_group_layout.addWidget(g12_container)
        self.g1_container_width = max(g11_container.sizeHint().width(), g12_container.sizeHint().width(), g1_container.sizeHint().width()) + gap12
    else:
        g_group_layout = QtWidgets.QHBoxLayout(self.g_group_widget)
        g_group_layout.addWidget(g12_container)
        g_group_layout.addWidget(g1_container)
        g_group_layout.addWidget(g11_container)
        self.g1_container_width = g11_container.sizeHint().width() + g1_container.sizeHint().width() + gap12 +small_gap - 4



    self.g1_placeholder = QtWidgets.QSpacerItem(self.g1_container_width, 1, QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    g_group_layout = QtWidgets.QHBoxLayout(self.e_group_widget)
    g_group_layout.addWidget(g3_container)

    if chat_mode:
        self.g_group_widget.setVisible(False)
    #layout.addLayout(g2_layout)
    # Create a parent horizontal layout to contain both groups side by side

    if isLTR:
        both_groups_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
        self.g1_layout_index = both_groups_layout.count()  # Get the index for the middle widget
        both_groups_layout.addWidget(self.e_group_widget)

        #both_groups_layout.addWidget(g11_container)
        both_groups_layout.addSpacing(gap12)
        both_groups_layout.addWidget(self.g_group_widget)
        both_groups_layout.addSpacing(20)
        both_groups_layout.addWidget(g2_container)
    else:
        both_groups_layout.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        self.g1_layout_index = both_groups_layout.count()  # Get the index for the middle widget
        both_groups_layout.addWidget(self.g_group_widget)

        # both_groups_layout.addWidget(g11_container)
        both_groups_layout.addSpacing(gap12)
        both_groups_layout.addWidget(self.e_group_widget)
        both_groups_layout.addSpacing(20)
        both_groups_layout.addWidget(g2_container)

    g1_container.setToolTip("איך לחפש, 1 האם כל המילה מופיעה 2 האם רק חלקה ")
    g2_container.setToolTip("ניקוי מסך התוצאות ומסך הבקשות")
    g3_container.setToolTip("איך לחפש. 1 מילים במסמך 2 לשאול את צ'אט GPT")

    # Create the label


    # Add the label to g1_container's layout


    g3_container.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    g2_container.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    g1_container.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    g11_container.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
    g12_container.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    #g1_container.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
    #g2_container.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)
    #g3_container.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft)

    self.g1_container = g1_container
    self.g3_container = g3_container
    self.g11_container = g11_container
    self.g12_container = g12_container
    self.both_groups_layout = both_groups_layout







    # Add this combined layout to your main layout
    layout.addLayout(both_groups_layout)

    self.progressBar = QtWidgets.QProgressBar()
    self.progressBar.setRange(0, 100)

    self.progressBar.setStyleSheet("""
    QProgressBar {
        border: 2px solid white;
        border-radius: 5px;
        text-align: right;
        color: black;
        background-color: #E0E0E0;
    }
    QProgressBar::chunk {
        background-color: blue;
        width: 10px;
        margin: 0.5px;
    }
    """)


    layout.addWidget(self.progressBar)  # Assuming 'layout' is your main layout

    # -------- Results display area --------
    self.results_area = QtWidgets.QTextBrowser()
    self.results_area.setOpenLinks(False)
    self.results_area.setReadOnly(True)
    self.results_area.setFont(font)
    if isLTR:
        self.results_area.setAlignment(QtCore.Qt.AlignLeft)
        self.results_area.setLayoutDirection(QtCore.Qt.LeftToRight)
    else:
        self.results_area.setAlignment(QtCore.Qt.AlignRight)
        self.results_area.setLayoutDirection(QtCore.Qt.RightToLeft)

    layout.addWidget(self.results_area)


    # (End of setup_ui method)

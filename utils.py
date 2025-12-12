CHECKBOX_STYLE_QSS_black ="""
                    QCheckBox {
                        background-color: black ; /* #f0f0f0 Light gray background for the frame */
                        color: #FFFFFF; /* Optional: set text color */
                        font-size: 20pt;
                        font-weight: bold;
                        padding: 5px; /* Optional: add internal padding */
                        border: 6px solid #FF0000;
                        border-radius: 6px;
                    }
                    QCheckBox::indicator {
                        width: 25px;
                        height: 25px;
                    }
                    """


QRadioButton_STYLE_QSS_green_1520bg ="""
            QRadioButton {
                background-color: #0000ff; /* Light gray background for the frame */
                color: #333333; /* Optional: set text color */
                padding: 5px; /* Optional: add internal padding */
            }
            QRadioButton::indicator {
                width: 15px;
                height: 20px;
                border-radius: 6px;
                border: 6px solid black;
            }
            QRadioButton::indicator:checked {
                background-color: green;
            }
            """

QRadioButton_STYLE_QSS_green_1616bg="""
                QRadioButton {
                    background-color: #0000ff; /* Light gray background for the frame */
                    color: #333333; /* Optional: set text color */
                    padding: 5px; /* Optional: add internal padding */
                }
                QRadioButton::indicator {
                    width: 16px;
                    height: 16px;
                    border-radius: 8;
                    border: 6px solid black;
                }
                QRadioButton::indicator:checked {
                    background-color: green;
                }
            """

QRadioButton_STYLE_QSS_green_1515bg="""
                QRadioButton {
                    background-color: #f0f0f0; /* Light gray background for the frame */
                    color: #333333; /* Optional: set text color */
                    padding: 5px; /* Optional: add internal padding */
                }
                QRadioButton::indicator {
                    width: 15px;
                    height: 15px;
                    border-radius: 10px;
                    border: 6px solid black;
                }
                QRadioButton::indicator:checked {
                    background-color: green;
                }
                """

CHECKBOX_STYLE_QSS_gray ="""
                    QCheckBox {
                        background-color: #f0f0f0 ; /*  Light gray background for the frame */
                        color: #000000; /* Optional: set text color */
                        font-size: 20pt;
                        font-weight: bold;
                        padding: 5px; /* Optional: add internal padding */
                        border: 6px solid #FF0000;
                        border-radius: 6px;
                    }
                    QCheckBox::indicator {
                        width: 25px;
                        height: 25px;
                    }
                    """

CHECKBOX_STYLE_QSS_red ="""
                    QCheckBox {
                        background-color: red ; /*  Light gray background for the frame */
                        color: #0000FF; /* Optional: set text color */
                        font-size: 20pt;
                        font-weight: bold;
                        padding: 5px; /* Optional: add internal padding */
                        border: 6px solid #FF0000;
                        border-radius: 6px;
                    }
                    QCheckBox::indicator {
                        width: 25px;
                        height: 25px;
                    }
                    """

CHECKBOX_STYLE_QSS_blue ="""
                    QCheckBox {
                        background-color: blue ; /*  Light gray background for the frame */
                        color: #0000FF; /* Optional: set text color */
                        font-size: 20pt;
                        font-weight: bold;
                        padding: 5px; /* Optional: add internal padding */
                        border: 6px solid #FF0000;
                        border-radius: 6px;
                    }
                    QCheckBox::indicator {
                        width: 25px;
                        height: 25px;
                    }
                    """

Container_STYLE_QSS="""
                 QWidget {
                     background-color: #00F0FF; /* Alice Blue background */
                     border: 2px solid #6495ED; /* Cornflower Blue border */
                     border-radius: 6px;
                     padding: 5px;
                 }
             """

Radio_STYLE_QSS_red="""
            QRadioButton::indicator {
                width: 15px;
                height: 15px;
                border-radius: 6px;
                border: 6px solid black;
            }
            QRadioButton::indicator:checked {
                background-color: red;
            }
        """

Radio_STYLE_QSS_green="""
                 QRadioButton::indicator {
                     width: 15px;
                     height: 15px;
                     border-radius: 6px;
                     border: 6px solid black;
                 }
                 QRadioButton::indicator:checked {
                     background-color: green;
                 }
             """
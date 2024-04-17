style = '''
        QMessageBox {{
            background-color: {_bg_color};
            color: {_text_color};
            border-radius: {_radius}px;
        }}
        QPushButton {{
            color: {_button_text_color};
            background-color: {_button_bg_color};
            border-radius: {_button_radius}px;
            padding: 6px;
        }}
        QPushButton:hover {{
            background-color: {_button_hover_bg_color};
        }}
        QPushButton:pressed {{
            background-color: {_button_pressed_bg_color};
        }}
        '''
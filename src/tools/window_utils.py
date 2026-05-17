import win32gui

def get_open_windows():
    """Возвращает список названий всех видимых окон в системе."""
    windows = []
    
    def enum_windows_callback(hwnd, lParam):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            # Игнорируем системные и пустые окна
            if title and title not in ["Program Manager", "Settings", "Microsoft Store"]:
                windows.append(title)
                
    win32gui.EnumWindows(enum_windows_callback, None)
    
    return sorted(list(set(windows)))

def get_window_rect(window_name):
    """Возвращает координаты окна (left, top, right, bottom) по названию."""
    hwnd = win32gui.FindWindow(None, window_name)
    if hwnd:
        return win32gui.GetWindowRect(hwnd)
    return None

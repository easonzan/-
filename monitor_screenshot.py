import tkinter as tk
from tkinter import filedialog, messagebox
import time
import datetime
import os
import mss
from PIL import Image, ImageTk
from skimage.metrics import structural_similarity as compare_ssim
import threading
import json
import sys
import numpy as np

class ScreenshotApp:
    CONFIG_FILE = "config.json"
    CONTROL_FRAME_WIDTH = 420
    CONTROL_FRAME_HEIGHT = 82

    # 优化颜色方案 - 使用更柔和的色调
    COLORS = {
        'primary': '#0078D4',    # Microsoft Blue
        'secondary': '#444791',  # Notion Purple
        'success': '#28A745',    # Bootstrap Green
        'danger': '#DC3545',     # Bootstrap Red
        'background': '#FFFFFF', # 纯白背景
        'text': '#242424',      # 深灰文字
        'border': '#E0E0E0',    # 边框颜色
        'hover': '#F5F5F5',     # 悬停背景色
    }

    def __init__(self):
        self.start_x = None
        self.start_y = None
        self.end_x = None
        self.rectangle = None
        self.selected_area = None
        self.screenshot_folder = None
        self.monitoring = False
        self.previous_image = None
        self.monitor_thread = None
        self.scale_factor = 1.0

        # 加载配置
        self.load_config()

        # 初始化主窗口
        self.root = tk.Tk()
        self.root.withdraw()

        # 计算 DPI 缩放因子
        self.adjust_for_dpi()

        # 记录初始窗口大小
        self.initial_width = int(self.CONTROL_FRAME_WIDTH * self.scale_factor)
        self.initial_height = int(self.CONTROL_FRAME_HEIGHT * self.scale_factor)

        # 初始化控制面板
        self.control_frame = tk.Toplevel(self.root)
        self.control_frame.title("智能截屏软件")
        self.control_frame.geometry(f"{self.initial_width}x{self.initial_height}")
        self.control_frame.resizable(False, False)
        self.control_frame.configure(bg=self.COLORS['background'])
        self.control_frame.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # 设置统一的按钮样式
        self.style = {
            'font': ('Microsoft YaHei UI', 9),
            'width': 9,
            'height': 1,
            'bd': 1,
            'relief': 'solid',
            'padx': 12,
            'pady': 4,
            'cursor': 'hand2',
            'borderwidth': 1,
        }

        # 创建主容器
        main_frame = tk.Frame(self.control_frame, bg=self.COLORS['background'])
        main_frame.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)

        # 创建按钮容器
        button_frame = tk.Frame(main_frame, bg=self.COLORS['background'])
        button_frame.pack(fill=tk.X)

        # 初始化控件
        self.select_area_button = self.create_button(
            button_frame, 
            "选定区域", 
            self.select_area,
            bg='white',
            fg=self.COLORS['primary'],
            activebackground=self.COLORS['hover'],
            activeforeground=self.COLORS['primary']
        )
        
        self.save_path_button = self.create_button(
            button_frame,
            "选择路径",
            self.choose_save_path,
            bg='white',
            fg=self.COLORS['secondary'],
            activebackground=self.COLORS['hover'],
            activeforeground=self.COLORS['secondary']
        )
        
        self.start_monitor_button = self.create_button(
            button_frame,
            "开始监控",
            self.start_monitoring,
            bg='white',
            fg=self.COLORS['success'],
            activebackground=self.COLORS['hover'],
            activeforeground=self.COLORS['success'],
            state="disabled"
        )
        
        self.stop_monitor_button = self.create_button(
            button_frame,
            "停止监控",
            self.stop_monitoring,
            bg='white',
            fg=self.COLORS['danger'],
            activebackground=self.COLORS['hover'],
            activeforeground=self.COLORS['danger'],
            state="disabled"
        )

        # 布局按钮 - 使用grid布局
        self.select_area_button.grid(row=0, column=0, padx=4)
        self.save_path_button.grid(row=0, column=1, padx=4)
        self.start_monitor_button.grid(row=0, column=2, padx=4)
        self.stop_monitor_button.grid(row=0, column=3, padx=4)

        # 配置grid列权重
        button_frame.grid_columnconfigure(0, weight=1)
        button_frame.grid_columnconfigure(1, weight=1)
        button_frame.grid_columnconfigure(2, weight=1)
        button_frame.grid_columnconfigure(3, weight=1)

        # 状态标签使用新样式
        self.status_label = tk.Label(
            main_frame,
            text="⚠️ 请选择保存路径",
            font=('Microsoft YaHei UI', 9),
            bg=self.COLORS['background'],
            fg=self.COLORS['text'],
            anchor="w"
        )
        self.status_label.pack(fill=tk.X, pady=(8, 0), padx=4)

        # 添加分隔线
        separator = tk.Frame(main_frame, height=1, bg=self.COLORS['border'])
        separator.pack(fill=tk.X, pady=(6, 0))

        # 如果已加载路径和区域，启用相关功能
        if self.screenshot_folder and self.selected_area:
            self.start_monitor_button.config(state="normal")
            self.update_status_label()

    def create_button(self, parent, text, command, **kwargs):
        """创建统一风格的按钮"""
        button_style = self.style.copy()
        button_style.update(kwargs)
        button = tk.Button(parent, text=text, command=command, **button_style)
        
        # 添加鼠标悬停效果
        def on_enter(e):
            if button['state'] != 'disabled':
                button.config(
                    bg=self.COLORS['hover'],
                    relief='solid'
                )
        
        def on_leave(e):
            if button['state'] != 'disabled':
                button.config(
                    bg='white',
                    relief='solid'
                )
            
        button.bind("<Enter>", on_enter)
        button.bind("<Leave>", on_leave)
        return button

    def lighten_color(self, color_hex):
        """使颜色变亮一些"""
        rgb = tuple(int(color_hex.lstrip('#')[i:i+2], 16) for i in (0, 2, 4))
        lighter_rgb = tuple(min(int(x * 1.2), 255) for x in rgb)
        return '#{:02x}{:02x}{:02x}'.format(*lighter_rgb)

    def load_config(self):
        """加载保存路径和区域配置"""
        if os.path.exists(self.CONFIG_FILE):
            with open(self.CONFIG_FILE, "r") as config_file:
                config = json.load(config_file)
                self.screenshot_folder = config.get("screenshot_folder")
                self.selected_area = config.get("selected_area")

    def save_config(self):
        """保存当前路径和区域到配置文件"""
        config = {
            "screenshot_folder": self.screenshot_folder,
            "selected_area": self.selected_area
        }
        with open(self.CONFIG_FILE, "w") as config_file:
            json.dump(config, config_file)

    def update_status_label(self):
        """更新状态栏样式和内容"""
        if self.screenshot_folder:
            max_length = 45
            path_info = self.screenshot_folder
            if len(path_info) > max_length:
                path_info = f"...{path_info[-max_length:]}"
            self.status_label.config(
                text=f"📁 {path_info}",
                fg=self.COLORS['text']
            )
        else:
            self.status_label.config(
                text="⚠️ 请选择保存路径",
                fg=self.COLORS['danger']
            )

    def adjust_for_dpi(self):
        """调整窗口大小以适配高 DPI"""
        dpi = self.root.winfo_fpixels('1i')
        self.scale_factor = dpi / 96
        print(f"DPI: {dpi}, Scale Factor: {self.scale_factor}")

    def select_area(self):
        """区域选择逻辑"""
        self.control_frame.withdraw()
        screenshot, monitor = self.get_fullscreen_screenshot()
        screen_width, screen_height, screen_left, screen_top = self.get_screen_size()

        self.overlay_window = tk.Toplevel(self.control_frame)
        self.overlay_window.geometry(f"{screen_width}x{screen_height}+{screen_left}+{screen_top}")
        self.overlay_window.attributes("-topmost", True)
        self.overlay_window.attributes("-alpha", 0.7)
        self.overlay_window.overrideredirect(True)

        self.overlay_canvas = tk.Canvas(self.overlay_window, width=screen_width, height=screen_height, cursor="cross", highlightthickness=0)
        self.overlay_canvas.pack(fill=tk.BOTH, expand=True)

        self.photo = ImageTk.PhotoImage(screenshot)
        self.overlay_canvas.create_image(0, 0, image=self.photo, anchor="nw")

        self.overlay_canvas.bind("<ButtonPress-1>", self.on_button_press)
        self.overlay_canvas.bind("<B1-Motion>", self.on_mouse_drag)
        self.overlay_canvas.bind("<ButtonRelease-1>", lambda event: self.on_button_release(event, monitor))
        self.overlay_window.bind("<Escape>", lambda event: self.cancel_selection())

    def get_fullscreen_screenshot(self):
        """获取全屏截图和屏幕信息"""
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            screenshot = sct.grab(monitor)
            image = Image.frombytes("RGB", (screenshot.width, screenshot.height), screenshot.rgb)
            return image, monitor

    def get_screen_size(self):
        """获取屏幕尺寸和位置"""
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            return monitor["width"], monitor["height"], monitor["left"], monitor["top"]

    def on_button_press(self, event):
        """按下鼠标键时设置起点"""
        self.start_x = event.x
        self.start_y = event.y
        if self.rectangle:
            self.overlay_canvas.delete(self.rectangle)
        self.rectangle = self.overlay_canvas.create_rectangle(
            self.start_x, self.start_y, self.start_x, self.start_y,
            outline=self.COLORS['primary'], width=2
        )

    def on_mouse_drag(self, event):
        """拖动鼠标时绘制矩形"""
        self.end_x = event.x
        self.end_y = event.y
        if self.rectangle:
            self.overlay_canvas.coords(self.rectangle, self.start_x, self.start_y, self.end_x, self.end_y)

    def on_button_release(self, event, monitor):
        """释放鼠标键时保存选区"""
        self.end_x = event.x
        self.end_y = event.y

        self.selected_area = {
            "top": monitor["top"] + min(self.start_y, self.end_y),
            "left": monitor["left"] + min(self.start_x, self.end_x),
            "width": abs(self.end_x - self.start_x),
            "height": abs(self.end_y - self.start_y)
        }
        self.update_status_label()
        self.save_config()

        self.overlay_window.destroy()
        self.control_frame.deiconify()

    def cancel_selection(self):
        """取消选择区域"""
        self.overlay_window.destroy()
        self.control_frame.deiconify()

    def choose_save_path(self):
        """选择保存路径"""
        path = filedialog.askdirectory()
        if path:
            self.screenshot_folder = path
            self.update_status_label()
            self.save_config()
            if self.selected_area:
                self.start_monitor_button.config(state="normal")

    def take_screenshot(self):
        """进行截图"""
        if not self.selected_area or not self.screenshot_folder:
            messagebox.showerror("错误", "请先选择区域和保存路径")
            return None

        with mss.mss() as sct:
            screenshot = sct.grab(self.selected_area)
            return Image.frombytes("RGB", (screenshot.width, screenshot.height), screenshot.rgb)

    def save_screenshot(self, image):
        """保存截图到文件"""
        if image:
            timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3]
            filename = os.path.join(self.screenshot_folder, f"screenshot_{timestamp}.png")
            image.save(filename)
            print(f"截图保存为: {filename}")

    def monitor(self):
        """截图监控逻辑"""
        while self.monitoring:
            image = self.take_screenshot()
            if image:
                current_gray = np.array(image.convert("L"))
                
                if self.previous_image is not None:
                    previous_gray = np.array(self.previous_image.convert("L"))
                    ssim_value, _ = compare_ssim(previous_gray, current_gray, full=True)
                    
                    if ssim_value > 0.95:
                        print("图片相似，跳过保存")
                        time.sleep(1)
                        continue
                
                self.save_screenshot(image)
                self.previous_image = image

            time.sleep(1)

    def start_monitoring(self):
        """开始监控"""
        if not self.selected_area or not self.screenshot_folder:
            messagebox.showerror("错误", "请先选择区域和保存路径")
            return

        self.monitoring = True
        self.start_monitor_button.config(state="disabled")
        self.stop_monitor_button.config(state="normal")
        self.status_label.config(text="🔄 正在监控中...")

        self.monitor_thread = threading.Thread(target=self.monitor)
        self.monitor_thread.start()

    def stop_monitoring(self):
        """停止监控"""
        self.monitoring = False
        self.start_monitor_button.config(state="normal")
        self.stop_monitor_button.config(state="disabled")
        self.update_status_label()
        self.previous_image = None

    def on_closing(self):
        """处理关闭窗口事件"""
        if self.monitoring:
            self.stop_monitoring()
        self.control_frame.destroy()
        self.root.destroy()
        sys.exit(0)

    def run(self):
        """运行主窗口"""
        self.control_frame.mainloop()

if __name__ == "__main__":
    app = ScreenshotApp()
    app.run()

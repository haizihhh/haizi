"""
Trust Chat - 局域网PC与手机互发消息的应用
基于 Kivy 框架的跨平台 GUI，支持文字消息、文件传输和图片传输

使用方法:
  python main.py
"""

import kivy
kivy.require('2.0.0')

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage
from kivy.uix.popup import Popup
from kivy.uix.filechooser import FileChooserListView
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.utils import platform as kivy_platform
from kivy.graphics import Color, Rectangle, RoundedRectangle
from kivy.metrics import dp
from kivy.uix.widget import Widget

import os
import sys
import threading
from datetime import datetime

# 添加当前目录到路径，确保可以导入 network 模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from network import NetworkManager, get_local_ip, get_device_name, format_file_size, get_received_dir

# ============ 窗口设置 ============

if kivy_platform in ('win', 'linux', 'macosx'):
    Window.size = (420, 720)
    Window.minimum_width = 320
    Window.minimum_height = 500

# ============ 聊天气泡组件 ============

class ChatBubble(BoxLayout):
    """文本消息气泡"""
    def __init__(self, text, is_sent, timestamp, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.size_hint_x = 0.78
        self.padding = [dp(10), dp(6)]
        self.spacing = dp(2)
        self.is_sent = is_sent

        # 文字内容
        self.msg_label = Label(
            text=text,
            size_hint_y=None,
            text_size=(dp(240), None),
            halign='left',
            valign='middle',
            color=(1, 1, 1, 1) if is_sent else (0.1, 0.1, 0.1, 1),
            markup=False,
        )
        self.msg_label.bind(texture_size=self._on_texture_size)
        self.add_widget(self.msg_label)

        # 时间戳
        self.time_label = Label(
            text=timestamp,
            size_hint_y=None,
            height=dp(16),
            font_size='10sp',
            halign='right',
            valign='bottom',
            color=(0.85, 0.85, 0.85, 1) if is_sent else (0.5, 0.5, 0.5, 1),
        )
        self.time_label.bind(texture_size=self._on_time_size)
        self.add_widget(self.time_label)

        # 气泡背景
        with self.canvas.before:
            if is_sent:
                Color(0.13, 0.59, 0.95, 1)   # 蓝色（自己发的）
            else:
                Color(0.92, 0.92, 0.92, 1)    # 灰色（收到的）
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._update_bg, size=self._update_bg)

    def _on_texture_size(self, instance, value):
        instance.height = value[1] + dp(4)
        self._recalc_height()

    def _on_time_size(self, instance, value):
        self._recalc_height()

    def _recalc_height(self):
        self.height = self.msg_label.height + self.time_label.height + dp(16)

    def _update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size


class FileBubble(BoxLayout):
    """文件/图片消息气泡"""
    def __init__(self, filepath, file_type, is_sent, timestamp, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.size_hint_y = None
        self.size_hint_x = 0.78
        self.padding = [dp(10), dp(6)]
        self.spacing = dp(4)
        self.is_sent = is_sent
        self.filepath = filepath

        if file_type == 'image' and os.path.exists(filepath):
            # 图片：显示缩略图
            self.img_widget = KivyImage(
                source=filepath,
                size_hint_y=None,
                height=dp(180),
                keep_ratio=True,
                allow_stretch=True,
            )
            self.add_widget(self.img_widget)
            self.bind(width=lambda inst, val: self._resize_image())
        else:
            # 普通文件：显示文件名和大小
            filename = os.path.basename(filepath)
            if os.path.exists(filepath):
                size_str = format_file_size(os.path.getsize(filepath))
            else:
                size_str = 'Unknown size'

            file_label = Label(
                text=f'[b]{filename}[/b]\n[size=11sp]{size_str}[/size]',
                size_hint_y=None,
                height=dp(44),
                markup=True,
                halign='left',
                valign='middle',
                color=(0.1, 0.1, 0.1, 1) if not is_sent else (1, 1, 1, 1),
            )
            self.add_widget(file_label)
            self._content_height = dp(50)

        # 时间戳
        self.time_label = Label(
            text=timestamp,
            size_hint_y=None,
            height=dp(16),
            font_size='10sp',
            halign='right',
            valign='bottom',
            color=(0.85, 0.85, 0.85, 1) if is_sent else (0.5, 0.5, 0.5, 1),
        )
        self.add_widget(self.time_label)

        # 背景
        with self.canvas.before:
            if is_sent:
                Color(0.13, 0.59, 0.95, 1)
            else:
                Color(0.92, 0.92, 0.92, 1)
            self.bg_rect = RoundedRectangle(pos=self.pos, size=self.size, radius=[dp(10)])
        self.bind(pos=self._update_bg, size=self._update_bg)

        self._update_height()

    def _resize_image(self):
        if hasattr(self, 'img_widget'):
            self.img_widget.width = self.width - dp(20)
            self._update_height()

    def _update_height(self):
        h = dp(20) + self.time_label.height  # padding + time
        if hasattr(self, 'img_widget'):
            h += self.img_widget.height
        elif hasattr(self, '_content_height'):
            h += self._content_height
        self.height = h

    def _update_bg(self, instance, value):
        self.bg_rect.pos = instance.pos
        self.bg_rect.size = instance.size


# ============ 文件选择弹窗 ============

class FilePickerPopup(Popup):
    """文件选择弹窗"""
    def __init__(self, file_type, on_select, **kwargs):
        super().__init__(**kwargs)
        self.title = 'Select File' if file_type == 'file' else 'Select Image'
        self.size_hint = (0.9, 0.8)
        self.auto_dismiss = False

        layout = BoxLayout(orientation='vertical', spacing=dp(4))

        # 文件浏览器
        filters = ['*'] if file_type == 'file' else ['*.png', '*.jpg', '*.jpeg', '*.gif', '*.bmp', '*.webp']
        self.filechooser = FileChooserListView(
            filters=filters,
            path=os.path.expanduser('~') if kivy_platform != 'android' else '/sdcard',
        )
        layout.add_widget(self.filechooser)

        # 按钮行
        btn_box = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6), padding=[dp(4), dp(4)])

        cancel_btn = Button(
            text='Cancel',
            background_color=(0.7, 0.7, 0.7, 1),
        )
        cancel_btn.bind(on_press=self.dismiss)
        btn_box.add_widget(cancel_btn)

        select_btn = Button(
            text='Select',
            background_color=(0.2, 0.6, 0.8, 1),
        )
        select_btn.bind(on_press=lambda x: self._do_select(on_select))
        btn_box.add_widget(select_btn)

        layout.add_widget(btn_box)
        self.content = layout

    def _do_select(self, callback):
        if self.filechooser.selection:
            filepath = self.filechooser.selection[0]
            self.dismiss()
            callback(filepath)


# ============ 主聊天界面 ============

class ChatScreen(BoxLayout):
    """主聊天界面"""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'

        # 网络管理器
        self.network = NetworkManager()

        # 构建 UI
        self._build_status_bar()
        self._build_chat_area()
        self._build_input_area()

        # 设置网络回调
        self._setup_network()

        # 启动网络服务
        Clock.schedule_once(lambda dt: self._start_network(), 0.3)

    # ---- 状态栏 ----

    def _build_status_bar(self):
        self.status_label = Label(
            text='Starting...',
            size_hint_y=None,
            height=dp(40),
            color=(1, 1, 1, 1),
            bold=True,
            halign='center',
            valign='middle',
        )
        with self.status_label.canvas.before:
            Color(0.2, 0.6, 0.8, 1)   # 蓝色
            self.status_rect = None
            self._bind_status_bg()
        self.add_widget(self.status_label)

    def _bind_status_bg(self):
        """绑定状态栏背景"""
        def update_bg(instance, value):
            instance.canvas.before.clear()
            Color(*(self._status_color))
            rect = Rectangle(pos=instance.pos, size=instance.size)
        self.status_label.bind(pos=update_bg, size=update_bg)

    @property
    def _status_color(self):
        if not hasattr(self, 'network'):
            return (0.2, 0.6, 0.8, 1)
        if self.network.connected:
            return (0.15, 0.7, 0.3, 1)   # 绿色 - 已连接
        elif self.network.running:
            return (0.2, 0.6, 0.8, 1)    # 蓝色 - 搜索中
        else:
            return (0.8, 0.3, 0.3, 1)    # 红色 - 断开

    # ---- 聊天区域 ----

    def _build_chat_area(self):
        self.chat_scroll = ScrollView(
            do_scroll_x=False,
            bar_width=dp(5),
            scroll_type=['bars', 'content'],
        )
        self.chat_list = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            spacing=dp(6),
            padding=[dp(8), dp(8)],
        )
        self.chat_list.bind(minimum_height=self.chat_list.setter('height'))
        self.chat_scroll.add_widget(self.chat_list)
        self.add_widget(self.chat_scroll)

    # ---- 输入区域 ----

    def _build_input_area(self):
        input_box = BoxLayout(
            orientation='vertical',
            size_hint_y=None,
            height=dp(108),
            spacing=dp(4),
            padding=[dp(6), dp(4)],
        )

        # 输入行：文本 + 发送按钮
        top_row = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))

        self.msg_input = TextInput(
            hint_text='Type a message...',
            multiline=False,
            size_hint_x=0.74,
            font_size='15sp',
            padding=[dp(8), dp(10)],
            background_color=(0.95, 0.95, 0.95, 1),
            foreground_color=(0.1, 0.1, 0.1, 1),
            cursor_color=(0.2, 0.6, 0.8, 1),
        )
        self.msg_input.bind(on_text_validate=lambda x: self.send_message())
        top_row.add_widget(self.msg_input)

        send_btn = Button(
            text='Send',
            size_hint_x=0.26,
            font_size='15sp',
            bold=True,
            background_color=(0.2, 0.6, 0.8, 1),
            background_normal='',
        )
        send_btn.bind(on_press=lambda x: self.send_message())
        top_row.add_widget(send_btn)
        input_box.add_widget(top_row)

        # 文件按钮行
        btn_row = BoxLayout(size_hint_y=None, height=dp(40), spacing=dp(6))

        file_btn = Button(
            text='Send File',
            font_size='14sp',
            background_color=(0.3, 0.7, 0.3, 1),
            background_normal='',
        )
        file_btn.bind(on_press=lambda x: self.pick_file())
        btn_row.add_widget(file_btn)

        img_btn = Button(
            text='Send Image',
            font_size='14sp',
            background_color=(0.9, 0.55, 0.15, 1),
            background_normal='',
        )
        img_btn.bind(on_press=lambda x: self.pick_image())
        btn_row.add_widget(img_btn)

        input_box.add_widget(btn_row)
        self.add_widget(input_box)

    # ---- 网络设置 ----

    def _setup_network(self):
        self.network.on_status = self._on_network_status
        self.network.on_message = self._on_network_message
        self.network.on_connected = self._on_network_connected
        self.network.on_disconnected = self._on_network_disconnected

        # 设置设备名称
        if kivy_platform == 'android':
            self.network.device_name = 'Phone'
        else:
            try:
                name = get_device_name()
                self.network.device_name = name if name and name != 'Unknown' else 'PC'
            except Exception:
                self.network.device_name = 'PC'

    def _start_network(self):
        self.network.start()
        # 使用本地 IP 更新设备名
        local_ip = get_local_ip()
        self._update_status_text(f'Searching... ({self.network.device_name} / {local_ip})')

    # ---- 网络回调（在后台线程调用，需要调度到主线程） ----

    def _on_network_status(self, text):
        Clock.schedule_once(lambda dt: self._update_status_text(text))

    def _on_network_connected(self, peer_name, peer_ip):
        Clock.schedule_once(lambda dt: self._update_status_text(f'Connected: {peer_name} ({peer_ip})'))

    def _on_network_disconnected(self):
        Clock.schedule_once(lambda dt: self._update_status_text('Disconnected. Searching...'))

    def _on_network_message(self, msg):
        """收到消息（在后台线程调用）"""
        Clock.schedule_once(lambda dt: self._display_received_message(msg))

    def _update_status_text(self, text):
        self.status_label.text = text
        # 更新背景色
        self.status_label.canvas.before.clear()
        if self.network.connected:
            Color(0.15, 0.7, 0.3, 1)   # 绿色
        elif self.network.running:
            Color(0.2, 0.6, 0.8, 1)    # 蓝色
        else:
            Color(0.8, 0.3, 0.3, 1)    # 红色
        Rectangle(pos=self.status_label.pos, size=self.status_label.size)

    # ---- 发送消息 ----

    def send_message(self):
        """发送文本消息"""
        text = self.msg_input.text.strip()
        if not text:
            return

        if not self.network.connected:
            self._show_popup('Not Connected', 'No device connected.\nMake sure both devices are on the same WiFi network.')
            return

        if self.network.send_text(text):
            timestamp = datetime.now().strftime('%H:%M')
            self._add_text_message(text, True, timestamp)
            self.msg_input.text = ''
        else:
            self._show_popup('Error', 'Failed to send message.')

    # ---- 文件选择 ----

    def pick_file(self):
        """选择文件发送"""
        if not self.network.connected:
            self._show_popup('Not Connected', 'No device connected.')
            return
        popup = FilePickerPopup('file', on_select=self._on_file_selected)
        popup.open()

    def pick_image(self):
        """选择图片发送"""
        if not self.network.connected:
            self._show_popup('Not Connected', 'No device connected.')
            return
        popup = FilePickerPopup('image', on_select=self._on_image_selected)
        popup.open()

    def _on_file_selected(self, filepath):
        """选择了文件"""
        def do_send():
            success = self.network.send_file(filepath, 'file')
            Clock.schedule_once(lambda dt: self._on_file_sent(filepath, 'file', success))

        threading.Thread(target=do_send, daemon=True).start()

    def _on_image_selected(self, filepath):
        """选择了图片"""
        def do_send():
            success = self.network.send_file(filepath, 'image')
            Clock.schedule_once(lambda dt: self._on_file_sent(filepath, 'image', success))

        threading.Thread(target=do_send, daemon=True).start()

    def _on_file_sent(self, filepath, file_type, success):
        """文件发送完成回调（主线程）"""
        if success:
            timestamp = datetime.now().strftime('%H:%M')
            self._add_file_message(filepath, file_type, True, timestamp)
        else:
            self._show_popup('Error', 'Failed to send file.\nThe connection may have been lost.')

    # ---- 消息显示 ----

    def _display_received_message(self, msg):
        """显示收到的消息（主线程调用）"""
        msg_type = msg['type']
        timestamp = msg['timestamp']

        if msg_type == 'text':
            self._add_text_message(msg['content'], False, timestamp)
        elif msg_type in ('file', 'image'):
            # 保存文件数据到本地
            filename = msg.get('name', 'unknown_file')
            data = msg.get('data', b'')

            save_dir = get_received_dir()
            os.makedirs(save_dir, exist_ok=True)

            filepath = os.path.join(save_dir, filename)
            # 处理重名
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(filepath):
                filepath = os.path.join(save_dir, f'{base}_{counter}{ext}')
                counter += 1

            try:
                with open(filepath, 'wb') as f:
                    f.write(data)
                self._add_file_message(filepath, msg_type, False, timestamp)
            except Exception as e:
                self._show_popup('Error', f'Failed to save file:\n{e}')

    def _add_text_message(self, text, is_sent, timestamp):
        """添加文本消息到聊天列表"""
        row = BoxLayout(size_hint_y=None, spacing=dp(4), padding=[0, dp(2)])

        bubble = ChatBubble(text, is_sent, timestamp)

        if is_sent:
            # 右对齐
            row.add_widget(Widget(size_hint_x=0.22))
            row.add_widget(bubble)
        else:
            # 左对齐
            row.add_widget(bubble)
            row.add_widget(Widget(size_hint_x=0.22))

        # 行高度 = 气泡高度 + 边距
        row.bind(children=lambda *args: self._update_row_height(row, bubble))
        row.height = bubble.height + dp(6)

        self.chat_list.add_widget(row)
        self._scroll_to_bottom()

    def _add_file_message(self, filepath, file_type, is_sent, timestamp):
        """添加文件/图片消息到聊天列表"""
        row = BoxLayout(size_hint_y=None, spacing=dp(4), padding=[0, dp(2)])

        bubble = FileBubble(filepath, file_type, is_sent, timestamp)

        if is_sent:
            row.add_widget(Widget(size_hint_x=0.22))
            row.add_widget(bubble)
        else:
            row.add_widget(bubble)
            row.add_widget(Widget(size_hint_x=0.22))

        row.height = bubble.height + dp(6)

        # 点击图片可查看大图
        if file_type == 'image' and os.path.exists(filepath):
            bubble.bind(on_touch_down=lambda inst, touch: self._on_image_tap(inst, touch, filepath))

        self.chat_list.add_widget(row)
        self._scroll_to_bottom()

    def _update_row_height(self, row, bubble):
        """更新行高度以匹配气泡"""
        row.height = bubble.height + dp(6)

    def _on_image_tap(self, instance, touch, filepath):
        """点击图片查看大图"""
        if instance.collide_point(*touch.pos):
            self._show_image_viewer(filepath)

    def _show_image_viewer(self, filepath):
        """显示大图查看器"""
        content = BoxLayout(orientation='vertical')

        img = KivyImage(source=filepath, keep_ratio=True, allow_stretch=True)
        content.add_widget(img)

        close_btn = Button(
            text='Close',
            size_hint_y=None,
            height=dp(40),
            background_color=(0.7, 0.7, 0.7, 1),
        )
        content.add_widget(close_btn)

        popup = Popup(
            title='Image Preview',
            content=content,
            size_hint=(0.9, 0.85),
        )
        close_btn.bind(on_press=popup.dismiss)
        popup.open()

    def _scroll_to_bottom(self):
        """滚动到聊天底部"""
        def do_scroll(dt):
            if self.chat_scroll.scroll_y is not None:
                self.chat_scroll.scroll_y = 0
        Clock.schedule_once(do_scroll, 0.05)

    # ---- 弹窗 ----

    def _show_popup(self, title, message):
        """显示信息弹窗"""
        content = BoxLayout(orientation='vertical', padding=dp(16), spacing=dp(12))

        msg_label = Label(
            text=message,
            halign='center',
            valign='middle',
        )
        content.add_widget(msg_label)

        ok_btn = Button(
            text='OK',
            size_hint_y=None,
            height=dp(40),
            background_color=(0.2, 0.6, 0.8, 1),
        )
        content.add_widget(ok_btn)

        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.7, 0.35),
            auto_dismiss=False,
        )
        ok_btn.bind(on_press=popup.dismiss)
        popup.open()

    # ---- 清理 ----

    def cleanup(self):
        """清理资源"""
        self.network.stop()


# ============ Kivy 应用 ============

class TrustApp(App):
    """Trust Chat 应用"""

    def build(self):
        self.title = 'Trust Chat'
        self.icon = ''

        screen = ChatScreen()
        self._screen = screen
        return screen

    def on_stop(self):
        """应用退出时清理"""
        if hasattr(self, '_screen'):
            self._screen.cleanup()


# ============ 入口 ============

if __name__ == '__main__':
    TrustApp().run()

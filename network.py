"""
网络通信模块 - 负责UDP设备发现和TCP消息/文件传输

协议设计:
  UDP发现 (端口 50008):
    广播 JSON: {"type": "hello", "name": "设备名", "ip": "本地IP", "port": 50009}
    每2秒广播一次，同时监听其他设备的广播

  TCP通信 (端口 50009):
    所有消息格式: [4字节: header长度][header JSON][4字节: data长度][data bytes]
    - 文本消息: header包含 {"type":"text","content":"...","timestamp":"..."}, data长度为0
    - 文件消息: header包含 {"type":"file","name":"...","timestamp":"..."}, data为文件二进制内容
    - 图片消息: header包含 {"type":"image","name":"...","timestamp":"..."}, data为图片二进制内容

  连接策略: IP地址较大的设备主动连接IP地址较小的设备，避免双方同时连接
"""

import socket
import threading
import json
import struct
import time
import os
from datetime import datetime
from kivy.utils import platform as kivy_platform

# ============ 常量 ============
DISCOVERY_PORT = 50008      # UDP 设备发现端口
CHAT_PORT = 50009           # TCP 聊天通信端口
BUFFER_SIZE = 65536         # 接收缓冲区大小
BROADCAST_INTERVAL = 2.0    # UDP 广播间隔（秒）

# ============ 辅助函数 ============

def get_local_ip():
    """获取本机在局域网中的IP地址"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            # 备用方案: 获取所有网络接口的IP
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip != '127.0.0.1':
                return ip
        except Exception:
            pass
        return '127.0.0.1'


def get_device_name():
    """获取设备名称"""
    try:
        return socket.gethostname()
    except Exception:
        return 'Unknown'


def get_received_dir():
    """获取接收文件的保存目录。
    在Android上使用公共Downloads目录以便用户直接访问；
    在其他平台上使用当前目录下的 received_files 文件夹。
    """
    if kivy_platform == 'android':
        # Android: 保存到公共 Downloads/TrustChat 目录
        return '/sdcard/TrustChat'
    else:
        return 'received_files'


def format_file_size(size_bytes):
    """格式化文件大小为可读形式"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f'{size_bytes:.1f} {unit}'
        size_bytes /= 1024
    return f'{size_bytes:.1f} TB'


# ============ 网络管理器 ============

class NetworkManager:
    """
    网络管理器 - 封装所有网络操作

    回调函数（由UI层设置）:
      on_status(text)         - 状态变化时调用
      on_message(msg)         - 收到消息时调用，msg为字典
      on_connected(name, ip)  - 建立连接时调用
      on_disconnected()       - 连接断开时调用
    """

    def __init__(self):
        self.device_name = 'Unknown'
        self.local_ip = get_local_ip()

        # 对端信息
        self.peer_ip = None
        self.peer_name = None

        # 套接字
        self.tcp_socket = None       # 当前TCP连接（可能是客户端或服务端接收的）
        self.tcp_server = None       # TCP服务端套接字
        self.udp_socket = None       # UDP套接字

        # 状态标志
        self.running = False
        self.connected = False

        # 回调函数
        self.on_status = None
        self.on_message = None
        self.on_connected = None
        self.on_disconnected = None

        # 线程安全锁
        self._send_lock = threading.Lock()
        self._connect_lock = threading.Lock()

        # 接收文件保存目录
        self.received_dir = get_received_dir()

    # ========== 启动/停止 ==========

    def start(self):
        """启动网络服务：UDP广播、UDP监听、TCP服务端"""
        if self.running:
            return
        self.running = True

        # 确保接收文件目录存在
        os.makedirs(self.received_dir, exist_ok=True)

        # 启动TCP服务器
        self._start_tcp_server()

        # 启动UDP广播和监听线程
        threading.Thread(target=self._udp_broadcast_loop, daemon=True, name='UDP-Broadcast').start()
        threading.Thread(target=self._udp_listen_loop, daemon=True, name='UDP-Listen').start()

        self._notify_status(f'Searching for devices... ({self.local_ip})')

    def stop(self):
        """停止所有网络服务"""
        self.running = False
        self.connected = False

        # 关闭TCP连接
        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except Exception:
                pass
            self.tcp_socket = None

        # 关闭TCP服务器
        if self.tcp_server:
            try:
                self.tcp_server.close()
            except Exception:
                pass
            self.tcp_server = None

        # 关闭UDP套接字
        if self.udp_socket:
            try:
                self.udp_socket.close()
            except Exception:
                pass
            self.udp_socket = None

    # ========== UDP 设备发现 ==========

    def _udp_broadcast_loop(self):
        """定期广播自身存在"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.udp_socket = sock

        while self.running:
            try:
                msg = json.dumps({
                    'type': 'hello',
                    'name': self.device_name,
                    'ip': self.local_ip,
                    'port': CHAT_PORT,
                })
                sock.sendto(msg.encode('utf-8'), ('255.255.255.255', DISCOVERY_PORT))
            except Exception:
                pass

            time.sleep(BROADCAST_INTERVAL)

        try:
            sock.close()
        except Exception:
            pass

    def _udp_listen_loop(self):
        """监听其他设备的广播"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(('0.0.0.0', DISCOVERY_PORT))
        sock.settimeout(1.0)

        while self.running:
            try:
                data, addr = sock.recvfrom(4096)
                msg = json.loads(data.decode('utf-8'))

                if msg.get('type') != 'hello':
                    continue

                peer_ip = msg.get('ip', addr[0])
                peer_name = msg.get('name', 'Unknown')

                # 忽略自己发出的广播
                if peer_ip == self.local_ip:
                    continue

                # 如果已经连接，忽略
                if self.connected:
                    continue

                # 决定谁发起连接：IP较大的设备主动连接IP较小的
                if self._should_connect(peer_ip):
                    self._notify_status(f'Found {peer_name} ({peer_ip}), connecting...')
                    threading.Thread(
                        target=self._connect_to,
                        args=(peer_ip, peer_name),
                        daemon=True,
                        name=f'TCP-Connect-{peer_ip}'
                    ).start()

            except socket.timeout:
                continue
            except json.JSONDecodeError:
                continue
            except Exception:
                continue

        try:
            sock.close()
        except Exception:
            pass

    def _should_connect(self, peer_ip):
        """
        判断是否应由我方主动连接对方。
        规则：IP地址较大的设备发起连接。这避免了双方同时连接对方。
        使用IP字符串比较（各段补齐3位）。
        """
        def ip_key(ip):
            try:
                parts = ip.split('.')
                return tuple(int(p) for p in parts)
            except Exception:
                return (0, 0, 0, 0)

        return ip_key(self.local_ip) > ip_key(peer_ip)

    # ========== TCP 服务器 ==========

    def _start_tcp_server(self):
        """启动TCP服务端，等待对方连接"""
        self.tcp_server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server.bind(('0.0.0.0', CHAT_PORT))
        self.tcp_server.listen(1)
        self.tcp_server.settimeout(1.0)

        threading.Thread(target=self._tcp_accept_loop, daemon=True, name='TCP-Accept').start()

    def _tcp_accept_loop(self):
        """等待对方TCP连接"""
        while self.running:
            try:
                client_sock, addr = self.tcp_server.accept()
                # 如果已经连接，拒绝新的连接
                if self.connected:
                    client_sock.close()
                    continue

                # 接收对方发送的握手信息
                client_sock.settimeout(5.0)
                try:
                    handshake_data = client_sock.recv(4096)
                    handshake = json.loads(handshake_data.decode('utf-8'))
                    peer_name = handshake.get('name', 'Unknown')
                except Exception:
                    peer_name = 'Unknown'

                client_sock.settimeout(None)  # 取消超时

                self.tcp_socket = client_sock
                self.peer_ip = addr[0]
                self.peer_name = peer_name
                self.connected = True

                self._notify_status(f'Connected: {peer_name} ({addr[0]})')
                if self.on_connected:
                    self.on_connected(peer_name, addr[0])

                # 开始接收消息
                self._tcp_receive_loop()

            except socket.timeout:
                continue
            except Exception:
                if self.running:
                    continue
                break

    # ========== 手动连接（供用户手动输入IP） ==========

    def manual_connect(self, peer_ip):
        """手动连接到指定IP，跳过UDP发现和IP大小判断"""
        if self.connected:
            return False, 'Already connected.'

        self._notify_status(f'Connecting to {peer_ip}...')

        with self._connect_lock:
            if self.connected:
                return False, 'Already connected.'

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((peer_ip, CHAT_PORT))

                handshake = json.dumps({'name': self.device_name})
                sock.sendall(handshake.encode('utf-8'))

                sock.settimeout(None)

                self.tcp_socket = sock
                self.peer_ip = peer_ip
                self.peer_name = 'Manual'
                self.connected = True

                self._notify_status(f'Connected: {peer_ip}')
                if self.on_connected:
                    self.on_connected(self.peer_name, peer_ip)

                threading.Thread(
                    target=self._tcp_receive_loop,
                    daemon=True,
                    name=f'TCP-Receive-{peer_ip}'
                ).start()

                return True, 'Connected.'

            except socket.timeout:
                self._notify_status('Connection timed out. Retrying auto-discovery...')
                return False, 'Connection timed out. Check the IP and try again.'

            except ConnectionRefusedError:
                self._notify_status('Connection refused. Retrying auto-discovery...')
                return False, 'Connection refused. Is Trust Chat running on the other device?'

            except OSError as e:
                self._notify_status('Connection failed. Retrying auto-discovery...')
                return False, f'Connection failed: {e}'

            except Exception as e:
                self._notify_status('Connection failed. Retrying auto-discovery...')
                return False, f'Connection failed: {e}'


    # ========== TCP 客户端（主动连接） ==========

    def _connect_to(self, peer_ip, peer_name):
        """主动连接到对方"""
        with self._connect_lock:
            if self.connected:
                return

            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(5.0)
                sock.connect((peer_ip, CHAT_PORT))

                # 发送握手信息（设备名）
                handshake = json.dumps({'name': self.device_name})
                sock.sendall(handshake.encode('utf-8'))

                sock.settimeout(None)  # 取消超时

                self.tcp_socket = sock
                self.peer_ip = peer_ip
                self.peer_name = peer_name
                self.connected = True

                self._notify_status(f'Connected: {peer_name} ({peer_ip})')
                if self.on_connected:
                    self.on_connected(peer_name, peer_ip)

                # 开始接收消息
                self._tcp_receive_loop()

            except Exception as e:
                self._notify_status(f'Connection failed: retrying...')
                # 连接失败，等待对方连接自己

    # ========== TCP 消息接收 ==========

    def _tcp_receive_loop(self):
        """TCP消息接收循环"""
        sock = self.tcp_socket

        while self.running and self.connected:
            try:
                sock.settimeout(1.0)

                # 1. 读取header长度（4字节，大端序）
                header_len_bytes = self._recv_exact(sock, 4)
                if header_len_bytes is None:
                    break
                header_len = struct.unpack('>I', header_len_bytes)[0]

                # 安全检查：header长度不能超过1MB
                if header_len > 1024 * 1024:
                    break

                # 2. 读取header JSON
                header_bytes = self._recv_exact(sock, header_len)
                if header_bytes is None:
                    break
                header = json.loads(header_bytes.decode('utf-8'))

                # 3. 读取data长度（4字节，大端序）
                data_len_bytes = self._recv_exact(sock, 4)
                if data_len_bytes is None:
                    break
                data_len = struct.unpack('>I', data_len_bytes)[0]

                # 安全检查：data长度不能超过500MB
                if data_len > 500 * 1024 * 1024:
                    break

                # 4. 读取data（如果有）
                data = b''
                if data_len > 0:
                    data = self._recv_exact(sock, data_len)
                    if data is None:
                        break

                # 5. 处理消息
                msg_type = header.get('type', 'text')
                timestamp = header.get('timestamp', '')

                msg = {
                    'type': msg_type,
                    'content': header.get('content', ''),
                    'name': header.get('name', ''),
                    'timestamp': timestamp,
                    'sender': self.peer_name,
                    'is_sent': False,
                    'data': data,
                    'data_len': data_len,
                }

                if self.on_message:
                    self.on_message(msg)

            except socket.timeout:
                continue
            except json.JSONDecodeError:
                continue
            except (ConnectionResetError, ConnectionAbortedError, OSError):
                break
            except Exception:
                break

        # 连接断开
        self._handle_disconnect()

    def _recv_exact(self, sock, n):
        """精确接收n字节数据，返回bytes或None（连接断开）"""
        data = b''
        while len(data) < n:
            try:
                chunk = sock.recv(n - len(data))
                if not chunk:
                    return None
                data += chunk
            except socket.timeout:
                # 超时，但我们需要继续等待（外层循环会重新设置超时）
                if not self.running or not self.connected:
                    return None
                continue
            except Exception:
                return None
        return data

    def _handle_disconnect(self):
        """处理连接断开"""
        was_connected = self.connected
        self.connected = False

        if self.tcp_socket:
            try:
                self.tcp_socket.close()
            except Exception:
                pass
            self.tcp_socket = None

        self.peer_ip = None
        self.peer_name = None

        if was_connected:
            self._notify_status('Disconnected. Searching for devices...')
            if self.on_disconnected:
                self.on_disconnected()

    def _notify_status(self, text):
        """通知状态变化（通过回调）"""
        if self.on_status:
            self.on_status(text)

    # ========== 发送消息 ==========

    def send_text(self, text):
        """发送文本消息"""
        if not self.connected or not self.tcp_socket:
            return False

        header = {
            'type': 'text',
            'content': text,
            'timestamp': datetime.now().strftime('%H:%M'),
        }
        return self._send_packet(header, b'')

    def send_file(self, filepath, file_type='file'):
        """发送文件（file_type可选 'file' 或 'image'）"""
        if not self.connected or not self.tcp_socket:
            return False

        if not os.path.exists(filepath):
            return False

        try:
            filename = os.path.basename(filepath)
            file_size = os.path.getsize(filepath)

            # 读取文件内容
            with open(filepath, 'rb') as f:
                file_data = f.read()

            header = {
                'type': file_type,
                'name': filename,
                'timestamp': datetime.now().strftime('%H:%M'),
            }
            return self._send_packet(header, file_data)

        except Exception as e:
            print(f'[NetworkManager] File send error: {e}')
            return False

    def _send_packet(self, header, data):
        """发送一个完整的消息包"""
        with self._send_lock:
            try:
                header_bytes = json.dumps(header).encode('utf-8')
                self.tcp_socket.sendall(struct.pack('>I', len(header_bytes)))
                self.tcp_socket.sendall(header_bytes)
                self.tcp_socket.sendall(struct.pack('>I', len(data)))
                if data:
                    self.tcp_socket.sendall(data)
                return True
            except Exception as e:
                print(f'[NetworkManager] Send error: {e}')
                self._handle_disconnect()
                return False

    # ========== 状态查询 ==========

    def is_connected(self):
        """是否已连接"""
        return self.connected

    def get_peer_info(self):
        """获取对端信息"""
        if self.connected:
            return {'name': self.peer_name, 'ip': self.peer_ip}
        return None

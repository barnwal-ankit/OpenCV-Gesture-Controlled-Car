import sys, time, socket, threading, requests
import cv2
import mediapipe as mp

from PyQt5.QtCore import QTimer, Qt, QByteArray, QRectF, QPointF
from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QComboBox, QSlider
)
from PyQt5.QtGui import QImage, QPixmap, QPainter, QLinearGradient, QColor, QTransform
from PyQt5.QtSvg import QSvgRenderer

############################################################
# CONFIG
############################################################
ESP_IP = "192.168.4.1"        # ESP AP/server IP
ESP_PORT = 8888               # UDP control port
BUFFER_SIZE = 1024

SEND_THROTTLE_SEC = 0.5
BATTERY_POLL_SEC = 3
CONNECTION_TIMEOUT_SEC = 6

VIDEO_W, VIDEO_H = 800, 600
ARENA_W, ARENA_H = 520, 260

ANIM_TICK_MS = 33
SCROLL_SPEED_F = 8
SCROLL_SPEED_B = -5
TILT_MAX_DEG = 30
TILT_EASE = 0.15
PARALLAX_EASE = 0.15

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.3)

# MediaPipe
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.6)


############################################################
# Helpers
############################################################
def count_fingers_ignore_thumb(lm_list):
    fingers = 0
    for tip in [8, 12, 16, 20]:
        if lm_list[tip][2] < lm_list[tip - 2][2]:
            fingers += 1
    return fingers


def crop_to_fit(frame, target_w, target_h):
    """Crop camera feed to fill QLabel without black borders."""
    h, w = frame.shape[:2]
    src_aspect = w / h
    dst_aspect = target_w / target_h
    if src_aspect > dst_aspect:
        new_w = int(h * dst_aspect)
        x0 = (w - new_w) // 2
        frame = frame[:, x0:x0 + new_w]
    else:
        new_h = int(w / dst_aspect)
        y0 = (h - new_h) // 2
        frame = frame[y0:y0 + new_h, :]
    return cv2.resize(frame, (target_w, target_h), interpolation=cv2.INTER_AREA)


############################################################
# Road Arena — perspective road;
############################################################
class RoadArena(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(ARENA_W, ARENA_H)
        self.setStyleSheet("background:#0b1020;border:2px solid #334155;border-radius:10px;")

        # Clean top-view car SVG
        svg_data = b"""
        <svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 80 160'>
          <defs>
            <radialGradient id='shadow' cx='50%' cy='80%' r='60%'>
              <stop offset='0%' stop-color='rgba(0,0,0,0.45)'/>
              <stop offset='100%' stop-color='rgba(0,0,0,0)'/>
            </radialGradient>
          </defs>
          <!-- Shadow -->
          <ellipse cx='40' cy='130' rx='26' ry='11' fill='url(#shadow)'/>
          <!-- Body -->
          <rect x='15' y='20' width='50' height='120' rx='20' ry='20' fill='#2563eb'/>
          <rect x='22' y='35' width='36' height='90' rx='12' ry='12' fill='#3b82f6'/>
          <!-- Windows -->
          <rect x='28' y='40' width='24' height='25' rx='6' ry='6' fill='#1e3a8a'/>
          <rect x='28' y='75' width='24' height='25' rx='6' ry='6' fill='#1e3a8a'/>
          <!-- Wheels -->
          <rect x='5'  y='35' width='10' height='30' rx='3' ry='3' fill='#111827'/>
          <rect x='5'  y='95' width='10' height='30' rx='3' ry='3' fill='#111827'/>
          <rect x='65' y='35' width='10' height='30' rx='3' ry='3' fill='#111827'/>
          <rect x='65' y='95' width='10' height='30' rx='3' ry='3' fill='#111827'/>
        </svg>
        """
        self.car_svg = QSvgRenderer(QByteArray(svg_data))
        self.car_size = (60, 120)

        self.cmd = 'S'
        self.scroll_y = 0.0
        self.target_dx = 0.0
        self.dx = 0.0
        self.target_tilt = 0.0
        self.tilt = 0.0

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(ANIM_TICK_MS)

    def set_command(self, cmd: str):
        self.cmd = cmd
        if cmd == 'L':
            self.target_tilt = -TILT_MAX_DEG
            self.target_dx = -30
        elif cmd == 'R':
            self.target_tilt = TILT_MAX_DEG
            self.target_dx = 30
        else:
            self.target_tilt = 0.0
            self.target_dx = 0.0

    def tick(self):
        if self.cmd == 'F':
            self.scroll_y += SCROLL_SPEED_F
        elif self.cmd == 'B':
            self.scroll_y += SCROLL_SPEED_B
        self.scroll_y %= 60
        self.dx += (self.target_dx - self.dx) * PARALLAX_EASE
        self.tilt += (self.target_tilt - self.tilt) * TILT_EASE
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()

        # Sky/ground gradient
        grad = QLinearGradient(0, 0, 0, h)
        grad.setColorAt(0.0, QColor("#0b1020"))
        grad.setColorAt(1.0, QColor("#1e293b"))
        p.fillRect(self.rect(), grad)

        # Perspective road
        top_y, bottom_y = int(h * 0.25), h
        half_top, half_bottom = int(w * 0.12), int(w * 0.44)
        road_grad = QLinearGradient(0, top_y, 0, bottom_y)
        road_grad.setColorAt(0.0, QColor("#1e293b"))
        road_grad.setColorAt(1.0, QColor("#111827"))
        p.setBrush(road_grad)
        p.setPen(Qt.NoPen)
        road = [
            QPointF(w/2 - half_top + self.dx*0.2, top_y),
            QPointF(w/2 + half_top + self.dx*0.2, top_y),
            QPointF(w/2 + half_bottom + self.dx, bottom_y),
            QPointF(w/2 - half_bottom + self.dx, bottom_y),
        ]
        p.drawPolygon(*road)

        # Lane dashes
        dash_gap = 60
        for i in range(-2, 12):
            y = top_y + i * dash_gap + self.scroll_y
            if top_y < y < h:
                t = (y - top_y) / (bottom_y - top_y + 1e-6)
                dash_w = 6 + 18 * t
                dash_h = 14 + 24 * t
                rect = QRectF(w/2 - dash_w/2 + self.dx*0.3, y, dash_w, dash_h)
                p.fillRect(rect, QColor("#e5e7eb"))

        # Car (centered, tilting)
        cw, ch = self.car_size
        cx, cy = w/2, int(h*0.65)
        p.save()
        tr = QTransform()
        tr.translate(cx, cy)
        tr.rotate(self.tilt)
        tr.translate(-cw/2, -ch/2)
        p.setTransform(tr)
        self.car_svg.render(p, QRectF(0, 0, cw, ch))
        p.restore()


############################################################
# Main GUI
############################################################

class ClickableSlider(QSlider):
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Compute new slider value from click position
            val = self.minimum() + (self.maximum() - self.minimum()) * event.x() / self.width()
            self.setValue(int(val))
            event.accept()
        super().mousePressEvent(event)


class SmartCarGUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Smart Car Control")
        self.setGeometry(80, 40, 1360, 760)
        self.setStyleSheet("background-color:#111827;color:#E5E7EB;font-family:'Segoe UI';")

        # Left: Camera
        self.video_label = QLabel()
        self.video_label.setFixedSize(VIDEO_W, VIDEO_H)
        self.video_label.setStyleSheet("border:2px solid #334155;border-radius:10px;background:black;")

        left = QVBoxLayout()
        left.addWidget(QLabel("Camera"))
        left.addWidget(self.video_label)
        left.addStretch(1)

        # Right: Animation + Controls
        self.arena = RoadArena()

        self.mode_box = QComboBox()
        self.mode_box.addItems(["Gesture Mode", "Manual Mode"])
        self.mode_box.setStyleSheet("""
        QComboBox {
            background: #1f2937;
            border: 1px solid #374151;
            padding: 10px 14px;
            font-size: 16px;
            min-height: 36px;
            color: #E5E7EB;
            border-radius: 8px;
        }
        QComboBox:hover { border: 1px solid #60a5fa; }
        QComboBox QAbstractItemView {
            background-color: #1f2937;
            selection-background-color: #2563eb;
            selection-color: white;
            border: 1px solid #374151;
        }
        """)

        self.speed_slider = ClickableSlider(Qt.Horizontal)
        self.speed_slider.setRange(0, 255)
        self.speed_slider.setValue(180)
        self.speed_label = QLabel("Speed: 180")

        def make_btn(txt):
            b = QPushButton(txt)
            b.setStyleSheet("QPushButton{background:#2563eb;color:white;border-radius:8px;padding:8px 12px;}")
            return b

        self.btn_f, self.btn_b = make_btn("Forward"), make_btn("Backward")
        self.btn_l, self.btn_r, self.btn_s = make_btn("Left"), make_btn("Right"), make_btn("Stop")

        self.conn_dot = QLabel(); self.conn_dot.setFixedSize(14,14)
        self.conn_dot.setStyleSheet("background:#B00020;border-radius:7px;")
        self.conn_label, self.batt_label = QLabel("Disconnected"), QLabel("Battery: N/A%")

        right = QVBoxLayout()
        right.addWidget(QLabel("Road Animation"))
        right.addWidget(self.arena)
        sp = QHBoxLayout(); sp.addWidget(QLabel("Speed")); sp.addWidget(self.speed_slider); sp.addWidget(self.speed_label)
        right.addLayout(sp)
        right.addWidget(QLabel("Mode")); right.addWidget(self.mode_box)
        m1=QHBoxLayout(); m1.addWidget(self.btn_l); m1.addWidget(self.btn_s); m1.addWidget(self.btn_r)
        right.addWidget(self.btn_f); right.addLayout(m1); right.addWidget(self.btn_b)
        srow=QHBoxLayout(); srow.addWidget(self.conn_dot); srow.addWidget(self.conn_label); srow.addStretch(1); srow.addWidget(self.batt_label)
        right.addLayout(srow); right.addStretch(1)

        root=QHBoxLayout(); root.addLayout(left); root.addSpacing(12); root.addLayout(right); self.setLayout(root)

        # ---- State ----
        self.cap=None
        self.timer=QTimer(self); self.timer.timeout.connect(self.tick_camera)
        self.ui_timer=QTimer(self); self.ui_timer.timeout.connect(self.refresh_conn); self.ui_timer.start(500)
        self.last_cmd='S'; self.last_send=0; self.last_rx=0; self.keep_threads=True; self.battery="N/A"
        self.current_speed = self.speed_slider.value()

        # Signals
        self.mode_box.currentTextChanged.connect(self.on_mode)
        self.speed_slider.valueChanged.connect(self.on_speed)
        self.btn_f.clicked.connect(lambda:self.drive('F'))
        self.btn_b.clicked.connect(lambda:self.drive('B'))
        self.btn_l.clicked.connect(lambda:self.drive('L'))
        self.btn_r.clicked.connect(lambda:self.drive('R'))
        self.btn_s.clicked.connect(lambda:self.drive('S'))

        threading.Thread(target=self.poll_battery,daemon=True).start()
        self.start_camera()
        self.on_mode(self.mode_box.currentText())
        self.on_speed(self.current_speed)  # initialize speed on ESP via HTTP

    # -------- Networking --------
    def send_udp(self,txt):
        try: sock.sendto(txt.encode(),(ESP_IP,ESP_PORT))
        except: pass

    def throttle(self,cmd):
        t=time.time()
        if cmd!=self.last_cmd or t-self.last_send>SEND_THROTTLE_SEC:
            self.send_udp(cmd)
            self.last_cmd=cmd
            self.last_send=t
            self.arena.set_command(cmd)

    def drive(self,cmd):
        if self.mode_box.currentText()=="Manual Mode":
            self.throttle(cmd)

    def on_speed(self,v):
        self.speed_label.setText(f"Speed: {v}")
        self.current_speed = v

        mapped_speed = int(100 + (v / 255) * (255 - 100))
        try:
            # Use the same endpoint as the embedded webpage
            requests.get(f"http://{ESP_IP}/setSpeed?value={mapped_speed}", timeout=0.5)
        except Exception as e:
            # Non-fatal; keep UI responsive
            print("Speed update failed:", e)

    def poll_battery(self):
        while self.keep_threads:
            try:
                self.send_udp('V')
                data,_=sock.recvfrom(BUFFER_SIZE)
                rep=data.decode().strip()
                if rep:
                    self.last_rx=time.time()
                    self.battery=rep.rstrip('%')
            except socket.timeout:
                pass
            except Exception:
                pass
            time.sleep(BATTERY_POLL_SEC)

    def refresh_conn(self):
        connected=(time.time()-self.last_rx)<CONNECTION_TIMEOUT_SEC
        self.conn_dot.setStyleSheet("background:#22C55E;border-radius:7px;" if connected else "background:#B00020;border-radius:7px;")
        self.conn_label.setText("Connected" if connected else "Disconnected")
        self.batt_label.setText(f"Battery:{self.battery}%")

    def on_mode(self,mode):
        man=(mode=="Manual Mode")
        for b in [self.btn_f,self.btn_b,self.btn_l,self.btn_r,self.btn_s]:
            b.setVisible(man)

    # -------- Camera + Overlay --------
    def start_camera(self):
        if self.cap is None:
            self.cap=cv2.VideoCapture(0)
            self.cap.set(3,1280)
            self.cap.set(4,720)
        if not self.timer.isActive(): self.timer.start(20)

    def tick_camera(self):
        ok,frame=self.cap.read()
        if not ok: return
        frame=cv2.flip(frame,1)

        cmd=None;text="STOP";color=(0,0,255)
        if self.mode_box.currentText()=="Gesture Mode":
            res=hands.process(cv2.cvtColor(frame,cv2.COLOR_BGR2RGB))
            if res.multi_hand_landmarks:
                for hnd in res.multi_hand_landmarks:
                    mp_draw.draw_landmarks(frame,hnd,mp_hands.HAND_CONNECTIONS)
                    h,w,_=frame.shape
                    lm=[[i,int(l.x*w),int(l.y*h)] for i,l in enumerate(hnd.landmark)]
                    if lm:
                        f=count_fingers_ignore_thumb(lm)
                        if f==1:cmd,text,color='F','FORWARD',(0,255,0)
                        elif f==2:cmd,text,color='B','BACKWARD',(0,165,255)
                        elif f==3:cmd,text,color='L','LEFT',(255,255,0)
                        elif f==4:cmd,text,color='R','RIGHT',(255,255,0)
                        else:cmd,text,color='S','STOP',(0,0,255)
            else:cmd,text,color='S','STOP',(0,0,255)
        else:
            cmd=self.last_cmd;text='Manual Control';color=(255,255,255)
        if cmd:self.throttle(cmd)

        # Draw overlays then crop-to-fit so they stay visible
        frame=crop_to_fit(frame,VIDEO_W,VIDEO_H)
        h,w=frame.shape[:2]; pad=20; line_h=30
        cv2.putText(frame,f"Mode: {self.mode_box.currentText()}",(pad,line_h),cv2.FONT_HERSHEY_SIMPLEX,0.7,(255,255,255),2)
        cv2.putText(frame,f"Command: {text}",(pad,line_h*2),cv2.FONT_HERSHEY_SIMPLEX,0.8,color,2)
        cv2.putText(frame,f"Speed:{self.current_speed}",(pad,line_h*3),cv2.FONT_HERSHEY_SIMPLEX,0.7,(255,255,0),2)
        cv2.putText(frame,f"Battery:{self.battery}%",(pad,line_h*4),cv2.FONT_HERSHEY_SIMPLEX,0.7,(0,255,0),2)
        rtxt="CONNECTED" if (time.time()-self.last_rx)<CONNECTION_TIMEOUT_SEC else "DISCONNECTED"
        rcol=(0,255,0) if rtxt=="CONNECTED" else (0,0,255)
        tsize=cv2.getTextSize(rtxt,cv2.FONT_HERSHEY_DUPLEX,0.8,2)[0]
        cv2.putText(frame,rtxt,(w-tsize[0]-pad,line_h),cv2.FONT_HERSHEY_DUPLEX,0.8,rcol,2)

        rgb=cv2.cvtColor(frame,cv2.COLOR_BGR2RGB)
        qimg=QImage(rgb.data,w,h,w*3,QImage.Format_RGB888)
        self.video_label.setPixmap(QPixmap.fromImage(qimg))

    def closeEvent(self,e):
        self.keep_threads=False
        if self.cap:self.cap.release()
        super().closeEvent(e)


if __name__=="__main__":
    app=QApplication(sys.argv)
    g=SmartCarGUI()
    g.show()
    sys.exit(app.exec_())

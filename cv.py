import cv2
import mediapipe as mp
import socket
import time
import threading

# ================= CONFIGURATION =================
ESP_IP = "192.168.4.1"
ESP_PORT = 8888
BUFFER_SIZE = 1024

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(0.2)

battery_level = "N/A"
keep_running = True

# ================= BATTERY THREAD =================
def fetch_battery():
    global battery_level
    while keep_running:
        try:
            sock.sendto(b'V', (ESP_IP, ESP_PORT))
            data, _ = sock.recvfrom(BUFFER_SIZE)
            battery_level = data.decode('utf-8')
        except socket.timeout:
            pass
        except Exception as e:
            print(f"Battery Error: {e}")
        time.sleep(3)

threading.Thread(target=fetch_battery, daemon=True).start()

# ================= MEDIAPIPE SETUP =================
mp_hands = mp.solutions.hands
hands = mp_hands.Hands(max_num_hands=1, min_detection_confidence=0.7, min_tracking_confidence=0.6)
mp_draw = mp.solutions.drawing_utils

# ================= HELPER FUNCTIONS =================
def count_fingers_ignore_thumb(lm_list):
    """Counts only index, middle, ring, and pinky fingers (ignores thumb)."""
    fingers = 0
    for tip in [8, 12, 16, 20]:
        if lm_list[tip][2] < lm_list[tip - 2][2]:
            fingers += 1
    return fingers

def send_command(cmd):
    try:
        sock.sendto(cmd.encode(), (ESP_IP, ESP_PORT))
    except Exception as e:
        print(f"Send Error: {e}")

# ================= MAIN LOOP =================
cap = cv2.VideoCapture(0)
cap.set(3, 640)
cap.set(4, 480)

print("Starting Camera... Press 'q' to exit.")

last_command = "S"
last_send_time = 0

while True:
    success, img = cap.read()
    if not success:
        break

    img = cv2.flip(img, 1)
    results = hands.process(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))

    command = "S"
    color = (0, 0, 255)
    status = "STOP"

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            mp_draw.draw_landmarks(img, hand_landmarks, mp_hands.HAND_CONNECTIONS)

            h, w, _ = img.shape
            lm_list = []
            for id, lm in enumerate(hand_landmarks.landmark):
                lm_list.append([id, int(lm.x * w), int(lm.y * h)])

            if lm_list:
                fingers = count_fingers_ignore_thumb(lm_list)

                # === GESTURE LOGIC ===
                if fingers == 1:
                    command, status, color = "F", "FORWARD", (0, 255, 0)
                elif fingers == 2:
                    command, status, color = "B", "BACKWARD", (0, 165, 255)
                elif fingers == 3:
                    command, status, color = "L", "LEFT", (255, 255, 0)
                elif fingers == 4:
                    command, status, color = "R", "RIGHT", (255, 255, 0)
                else:
                    command, status, color = "S", "STOP", (0, 0, 255)

                # Optional: show finger count
                cv2.putText(img, f"Fingers (no thumb): {fingers}", (20, 420),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 2)

    # Send command to car (with throttle)
    if command != last_command or time.time() - last_send_time > 0.5:
        send_command(command)
        last_command = command
        last_send_time = time.time()

    # === CLEAN UI OVERLAY (no banner) ===
    # Battery (Top Left)
    cv2.putText(img, f"Battery {battery_level}%", (15, 40),
                cv2.FONT_HERSHEY_DUPLEX, 0.9, (0, 255, 255), 2)

    # Status (Top Right)
    text_size = cv2.getTextSize(status, cv2.FONT_HERSHEY_DUPLEX, 1.3, 3)[0]
    cv2.putText(img, status, (640 - text_size[0] - 20, 45),
                cv2.FONT_HERSHEY_DUPLEX, 1.3, color, 3)

    # Command info (Bottom)
    cv2.putText(img,
                "1:FWD | 2:BACK | 3:LEFT | 4:RIGHT | else:STOP (thumb ignored)",
                (15, 465),
                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (200, 200, 200), 1)

    cv2.imshow("Gesture Car (Clean UI)", img)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        keep_running = False
        break

cap.release()
cv2.destroyAllWindows()
sock.close()

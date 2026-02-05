# 🚗 Gesture-Controlled Smart Car with Computer Vision

A **real-time gesture-controlled smart car system** powered by **OpenCV**, **MediaPipe**, and **ESP-based wireless control**.
The project allows a user to control a robotic car using **hand gestures captured by a camera**, with both a **minimal OpenCV interface** and an **advanced PyQt5 GUI** featuring animations, manual override, speed control, and battery monitoring.

---

## ✨ Features

* ✋ **Hand Gesture Recognition**

  * Uses MediaPipe Hands to detect fingers in real time
  * Thumb ignored for stability
* 📡 **Wireless ESP Communication**

  * UDP commands for movement
  * Battery level feedback from the car
* 🖥️ **Two Control Interfaces**

  * Lightweight OpenCV window (fast & simple)
  * Full PyQt5 GUI with animations and manual mode
* 🎮 **Dual Control Modes**

  * Gesture Mode (camera-based)
  * Manual Mode (buttons + speed slider)
* 🔋 **Live Battery Monitoring**
* 🛣️ **Animated Road Visualization**

  * Smooth car tilt, parallax, and scrolling road effect

---

## 🧠 Gesture Mapping

| Fingers (Thumb Ignored) | Action   | Command |
| ----------------------- | -------- | ------- |
| 1 Finger                | Forward  | `F`     |
| 2 Fingers               | Backward | `B`     |
| 3 Fingers               | Left     | `L`     |
| 4 Fingers               | Right    | `R`     |
| Any Other               | Stop     | `S`     |

---

## 🗂️ Project Structure

```text
.
├── cv.py               # Lightweight OpenCV-based gesture controller
├── cv_gui.py           # Full PyQt5 GUI with animation & manual control
├── opencv_car.ino      # ESP microcontroller firmware
└── README.md           # Project documentation
```

---

## 🧩 Components Overview

### 1️⃣ `cv.py` — Minimal Gesture Controller

* Pure OpenCV + MediaPipe implementation
* Clean HUD with:

  * Current command
  * Battery level
  * Finger count
* Sends UDP commands directly to the ESP
  📌 Best for **testing**, **low-latency demos**, or **headless setups**


---

### 2️⃣ `cv_gui.py` — Advanced Desktop Application

* Built with **PyQt5**
* Features:

  * Live camera feed
  * Gesture & Manual modes
  * Speed slider (mapped to ESP motor PWM)
  * Animated road + car visualization
  * Connection & battery status indicators
* Gesture recognition identical to `cv.py`, but with richer UI
  📌 Best for **presentations**, **user demos**, and **final projects**


---

### 3️⃣ `opencv_car.ino` — ESP Firmware

* Runs on an ESP-based microcontroller
* Responsibilities:

  * Receive UDP commands (`F`, `B`, `L`, `R`, `S`)
  * Control motors accordingly
  * Report battery voltage on request
  * Accept speed updates via HTTP endpoint

---

## ⚙️ Requirements

### Hardware

* ESP-based smart car (ESP8266 / ESP32)
* Motor driver (L298N, L293D, etc.)
* Camera (USB or laptop webcam)
* Battery with voltage sensing

### Software

* Python 3.8+
* Arduino IDE

### Python Dependencies

```bash
pip install opencv-python mediapipe PyQt5 requests
```

---

## ▶️ How to Run

### 🔹 Option 1: Simple OpenCV Controller

```bash
python cv.py
```

### 🔹 Option 2: Full GUI Application

```bash
python cv_gui.py
```

Make sure:

* The ESP is powered on
* Your computer is connected to the ESP’s Wi-Fi network
* The ESP IP matches:

```python
ESP_IP = "192.168.4.1"
```

---

## 🌐 Communication Protocol

### UDP Commands

| Command | Meaning         |
| ------- | --------------- |
| `F`     | Forward         |
| `B`     | Backward        |
| `L`     | Left            |
| `R`     | Right           |
| `S`     | Stop            |
| `V`     | Battery Request |

### HTTP

* Speed control via:

```text
http://<ESP_IP>/setSpeed?value=<PWM>
```

#include <ESP8266WiFi.h>
#include <ESP8266WebServer.h>
#include <WiFiUdp.h>

// ================= PIN DEFINITIONS =================
const int PIN_ENA = D5;  // Left motor speed
const int PIN_IN1 = D6;  // Left motor direction 1
const int PIN_IN2 = D7;  // Left motor direction 2
const int PIN_IN3 = D0;  // Right motor direction 1
const int PIN_IN4 = D1;  // Right motor direction 2
const int PIN_ENB = D2;  // Right motor speed

const int PIN_BAT = A0;  // Battery Sense Pin

// ================= WIFI SETTINGS =================
// You can use AP Mode (Car creates WiFi) or STA Mode (Connects to Router)
// Uncomment ONE of the following sections:

// OPTION A: Access Point Mode (Laptop connects to Car)
const char* ssid = "OpenCV_Car";
const char* password = "password123";
bool useAP = true;

// OPTION B: Station Mode (Car connects to your Home WiFi)
// const char* ssid = "YOUR_WIFI_NAME";
// const char* password = "YOUR_WIFI_PASSWORD";
// bool useAP = false;

// ================= GLOBALS =================
ESP8266WebServer server(80);
WiFiUDP udp;
unsigned int localUdpPort = 8888;
char packetBuffer[255]; 
int currentSpeed = 150; // PWM Speed (0-255)

// Battery Calculation
// Update these based on your voltage divider resistors
// Example for 2-cell LiPo (8.4V max) mapped to 3.3V range
float dividerRatio = 1.493; // Calibrate this value! (V_actual / V_measured)

void setup() {
  // Pin Modes
  pinMode(PIN_ENA, OUTPUT);
  pinMode(PIN_IN1, OUTPUT);
  pinMode(PIN_IN2, OUTPUT);
  pinMode(PIN_IN3, OUTPUT);
  pinMode(PIN_IN4, OUTPUT);
  pinMode(PIN_ENB, OUTPUT);
  pinMode(PIN_BAT, INPUT);
  
  // Stop motors initially
  stopCar();

  Serial.begin(115200);
  Serial.println("\nStarting OpenCV Car...");

  // WiFi Setup
  if (useAP) {
    WiFi.softAP(ssid, password);
    Serial.print("AP Created. IP: ");
    Serial.println(WiFi.softAPIP());
  } else {
    WiFi.begin(ssid, password);
    while (WiFi.status() != WL_CONNECTED) {
      delay(500);
      Serial.print(".");
    }
    Serial.print("\nConnected! IP: ");
    Serial.println(WiFi.localIP());
  }

  // Start UDP for OpenCV
  udp.begin(localUdpPort);
  Serial.print("UDP Listening on port: ");
  Serial.println(localUdpPort);

  // Start Web Server for Manual Control
  server.on("/", handleRoot);
  server.on("/cmd", handleWebCommand);
  server.on("/setSpeed", handleSetSpeed); // <-- add this line
  server.begin();
  Serial.println("HTTP Server started");
}

void loop() {
  server.handleClient(); // Handle Web requests
  checkUDP();            // Handle OpenCV commands
}

// ================= MOTOR CONTROL =================
void moveForward() {
  digitalWrite(PIN_IN1, HIGH); digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, HIGH); digitalWrite(PIN_IN4, LOW);
  analogWrite(PIN_ENA, currentSpeed); analogWrite(PIN_ENB, currentSpeed);
  Serial.println("Motor: Forward");
}

void moveBackward() {
  digitalWrite(PIN_IN1, LOW); digitalWrite(PIN_IN2, HIGH);
  digitalWrite(PIN_IN3, LOW); digitalWrite(PIN_IN4, HIGH);
  analogWrite(PIN_ENA, currentSpeed); analogWrite(PIN_ENB, currentSpeed);
  Serial.println("Motor: Backward");
}

void turnLeft() {
  digitalWrite(PIN_IN1, LOW); digitalWrite(PIN_IN2, HIGH);
  digitalWrite(PIN_IN3, HIGH); digitalWrite(PIN_IN4, LOW);
  analogWrite(PIN_ENA, currentSpeed); analogWrite(PIN_ENB, currentSpeed);
  Serial.println("Motor: Left");
}

void turnRight() {
  digitalWrite(PIN_IN1, HIGH); digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW); digitalWrite(PIN_IN4, HIGH);
  analogWrite(PIN_ENA, currentSpeed); analogWrite(PIN_ENB, currentSpeed);
  Serial.println("Motor: Right");
}

void stopCar() {
  digitalWrite(PIN_IN1, LOW); digitalWrite(PIN_IN2, LOW);
  digitalWrite(PIN_IN3, LOW); digitalWrite(PIN_IN4, LOW);
  analogWrite(PIN_ENA, 0); analogWrite(PIN_ENB, 0);
  Serial.println("Motor: Stop");
}

// ================= BATTERY LOGIC =================
int getBatteryPercentage() {
  int raw = analogRead(PIN_BAT);
  // NodeMCU raw 0-1023 maps to 0-3.3V at the pin
  // If using a voltage divider, adjust math below.
  // Assuming a 2-cell LiPo (max 8.4V, min 6.0V)
  // Voltage at Pin = raw * (3.3 / 1023.0)
  // Actual Battery V = Voltage at Pin * dividerRatio
  
  float voltage = (raw * (3.3 / 1023.0)) * dividerRatio;
  
  // Map 3.0V (0%) to 4.2V (100%)
  int percent = map((long)(voltage * 100), 300, 420, 0, 100);
  percent = constrain(percent, 0, 100);
  return percent;
}

// ================= UDP HANDLER (For Python/OpenCV) =================
void checkUDP() {
  int packetSize = udp.parsePacket();
  if (packetSize) {
    int len = udp.read(packetBuffer, 255);
    if (len > 0) packetBuffer[len] = 0;
    
    char cmd = packetBuffer[0];
    
    // Control Logic
    if (cmd == 'F') moveForward();
    else if (cmd == 'B') moveBackward();
    else if (cmd == 'L') turnLeft();
    else if (cmd == 'R') turnRight();
    else if (cmd == 'S') stopCar();
    else if (cmd == 'V') { 
      // Request for Voltage/Battery
      // Send back the percentage
      String batMsg = String(getBatteryPercentage());
      udp.beginPacket(udp.remoteIP(), udp.remotePort());
      udp.print(batMsg);
      udp.endPacket();
    }
  }
}

// ================= WEB SERVER HANDLERS =================
// --- Add this handler ---
void handleSetSpeed() {
  if (server.hasArg("value")) {
    currentSpeed = server.arg("value").toInt();
    if (currentSpeed < 0) currentSpeed = 0;
    if (currentSpeed > 255) currentSpeed = 255;
    Serial.println("Speed updated to: " + String(currentSpeed));
  }
  server.send(200, "text/plain", "OK");
}

// --- Updated main page ---
void handleRoot() {
  String html = "<html><head><meta name='viewport' content='width=device-width, initial-scale=1.0'>";
  html += "<style>";
  html += "button{width:100px;height:50px;font-size:20px;margin:5px;}";
  html += "input[type=range]{width:80%;height:30px;}";
  html += "</style></head><body>";
  html += "<center><h1>WiFi Car Control</h1>";

  // Battery info
  html += "<h3>Battery: " + String(getBatteryPercentage()) + "%</h3>";

  // Speed control section
  html += "<h3>Speed Control</h3>";
  html += "<input type='range' min='120' max='255' value='" + String(currentSpeed) + "' id='speedSlider' oninput='updateSpeed(this.value)'>";
  html += "<p>Current Speed: <span id='speedVal'>" + String(currentSpeed) + "</span></p>";

  // Movement buttons
  html += "<button onclick=\"location.href='/cmd?move=F'\">Forward</button><br>";
  html += "<button onclick=\"location.href='/cmd?move=L'\">Left</button>";
  html += "<button onclick=\"location.href='/cmd?move=S'\">Stop</button>";
  html += "<button onclick=\"location.href='/cmd?move=R'\">Right</button><br>";
  html += "<button onclick=\"location.href='/cmd?move=B'\">Backward</button>";

  // JavaScript for live speed update
  html += "<script>";
  html += "function updateSpeed(val){";
  html += "document.getElementById('speedVal').innerText=val;";
  html += "fetch('/setSpeed?value='+val);";
  html += "}";
  html += "</script>";

  html += "</center></body></html>";

  server.send(200, "text/html", html);
}

void handleWebCommand() {
  if (server.hasArg("move")) {
    String moveCmd = server.arg("move");
    if (moveCmd == "F") moveForward();
    else if (moveCmd == "B") moveBackward();
    else if (moveCmd == "L") turnLeft();
    else if (moveCmd == "R") turnRight();
    else if (moveCmd == "S") stopCar();
  }
  server.sendHeader("Location", "/");
  server.send(303);
}
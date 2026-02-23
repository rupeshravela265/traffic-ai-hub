# python -m pip install fastapi uvicorn pydantic passlib bcrypt==4.0.1
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import cv2
from ultralytics import YOLO
from fastapi.responses import StreamingResponse
# ... followed by your existing imports like FastAPI, sqlite3, etc.
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from passlib.context import CryptContext
import sqlite3
import random
import time
import logging
import uvicorn
import webbrowser
import os
import threading
# Load the model globally so it's ready before the first request

logging.getLogger("passlib").setLevel(logging.ERROR)

# ... existing imports above ...

app = FastAPI()

try:
    yolo_model = YOLO("yolov8n.pt") 
except Exception as e:
    print(f"Model Load Error: {e}")

# THESE LINES MUST BE AT THE VERY EDGE (ZERO SPACES)
EMERGENCY_CLASSES = ['ambulance', 'fire truck', 'police car']
is_emergency_active = False
active_violations = [] 

app.add_middleware(
    CORSMiddleware,
# ... rest of the code ...    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

# ===================== MODELS =====================

class UserRegister(BaseModel):
    username: str
    password: str
    email: str
    phone: str

class UserLogin(BaseModel):
    username: str
    password: str

class UserUpdate(BaseModel):
    username: str
    email: str
    phone: str

# ===================== UTILITIES =====================

def generate_otp():
    return str(random.randint(100000, 999999))

def otp_expired(expiry):
    return expiry is None or time.time() > expiry

# ===================== DATABASE =====================

def init_db():
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("PRAGMA user_version")
    version = cursor.fetchone()[0]

    if version < 1:
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                username TEXT UNIQUE,
                password TEXT
            )
        """)
        cursor.execute("PRAGMA user_version = 1")

    if version < 2:
        cursor.execute("ALTER TABLE users ADD COLUMN email TEXT")
        cursor.execute("ALTER TABLE users ADD COLUMN phone TEXT")
        cursor.execute("PRAGMA user_version = 2")

    if version < 3:
        cursor.execute("ALTER TABLE users ADD COLUMN email_verified INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN phone_verified INTEGER DEFAULT 0")
        cursor.execute("ALTER TABLE users ADD COLUMN email_otp TEXT")
        cursor.execute("ALTER TABLE users ADD COLUMN phone_otp TEXT")
        cursor.execute("ALTER TABLE users ADD COLUMN otp_expiry INTEGER")
        cursor.execute("PRAGMA user_version = 3")

    admin_pass = pwd_context.hash("admin123")
    cursor.execute("""
        INSERT OR REPLACE INTO users 
        (username, password, email, phone, email_verified, phone_verified)
        VALUES (?, ?, ?, ?, 1, 1)
    """, ("admin", admin_pass, "admin@traffic.ai", "+1000000000"))

    conn.commit()
    conn.close()

init_db()

# ===================== AUTH =====================

@app.post("/register")
async def register(user: UserRegister):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    try:
        hashed = pwd_context.hash(user.password)
        cursor.execute("""
            INSERT INTO users 
            (username, password, email, phone, email_verified, phone_verified)
            VALUES (?, ?, ?, ?, 0, 0)
        """, (user.username, hashed, user.email, user.phone))
        conn.commit()
        return {"message": "Registered. Verification required."}
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=400, detail="User already exists")
    finally:
        conn.close()

@app.post("/login")
async def login(user: UserLogin):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT password, email, phone, email_verified, phone_verified
        FROM users WHERE username=?
    """, (user.username,))
    row = cursor.fetchone()
    conn.close()

    if not row or not pwd_context.verify(user.password, row[0]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not row[3] or not row[4]:
        raise HTTPException(status_code=403, detail="Verify email and phone first")

    return {
        "message": "Verified",
        "user": user.username,
        "email": row[1],
        "phone": row[2]
    }

# ===================== PROFILE =====================

@app.post("/update-profile")
async def update_profile(data: UserUpdate):
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET email=?, phone=? WHERE username=?
    """, (data.email, data.phone, data.username))
    conn.commit()
    conn.close()
    return {"message": "Profile updated"}

# ===================== OTP EMAIL =====================
# SETTINGS (Use your real Gmail and App Password)
SENDER_EMAIL = "your-gmail@gmail.com"
SENDER_PASSWORD = "your-16-char-app-password"

@app.post("/send-email-otp")
async def send_email_otp(request: Request):
    data = await request.json()
    email = data["email"]
    otp = generate_otp()
    expiry = int(time.time() + 300) # 5 minutes

    # 1. Update Database
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET email_otp=?, otp_expiry=? WHERE email=?", (otp, expiry, email))
    conn.commit()
    conn.close()

    # 2. SEND REAL EMAIL
    try:
        msg = MIMEMultipart()
        msg['From'] = f"Traffic.AI Security <{SENDER_EMAIL}>"
        msg['To'] = email
        msg['Subject'] = f"Your Verification Code: {otp}"

        body = f"""
        <html>
            <body style="font-family: sans-serif; background-color: #0b0e14; color: white; padding: 20px;">
                <h1 style="color: #3b82f6;">Traffic.AI Master Hub</h1>
                <p>Use the following code to verify your operator identity:</p>
                <div style="background: #1e293b; padding: 20px; font-size: 32px; font-weight: bold; letter-spacing: 10px; text-align: center; border-radius: 10px;">
                    {otp}
                </div>
                <p style="color: #64748b; font-size: 12px; margin-top: 20px;">This code expires in 5 minutes.</p>
            </body>
        </html>
        """
        msg.attach(MIMEText(body, 'html'))

        # Connect to Google SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.send_message(msg)
        server.quit()

        return {"message": "Verification code sent to your inbox"}
    except Exception as e:
        print(f"Mail Error: {e}")
        raise HTTPException(status_code=500, detail="Failed to send email. Check your SMTP settings.")
# ===================== OTP PHONE =====================

@app.post("/send-phone-otp")
async def send_phone_otp(request: Request):
    data = await request.json()
    phone = data["phone"]

    otp = generate_otp()
    expiry = int(time.time() + 300)

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        UPDATE users SET phone_otp=?, otp_expiry=? WHERE phone=?
    """, (otp, expiry, phone))
    conn.commit()
    conn.close()


    print(f"[PHONE OTP] {phone} -> {otp}")
    return {"message": "Phone OTP sent"}

@app.post("/verify-phone-otp")
async def verify_phone_otp(request: Request):
    data = await request.json()
    phone, otp = data["phone"], data["otp"]

    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT phone_otp, otp_expiry FROM users WHERE phone=?
    """, (phone,))
    row = cursor.fetchone()

    if not row or row[0] != otp or otp_expired(row[1]):
        conn.close()
        raise HTTPException(status_code=400, detail="Invalid OTP")

    cursor.execute("""
        UPDATE users SET phone_verified=1, phone_otp=NULL WHERE phone=?
    """, (phone,))
    conn.commit()
    conn.close()
    return {"verified": True}

# ===================== AI INTELLIGENCE =====================

# --- Ensure these are at the top of auth.py ---
active_violations = [] 
is_emergency_active = False

@app.get("/ai-stats")
async def ai_stats():
    global active_violations, is_emergency_active
    # This sends the real-time violation list to your React frontend
    return {
        "vehicle_count": random.randint(10, 30), 
        "density": "MODERATE",
        "emergency_detected": is_emergency_active,
        "location": {"lat": 28.6139, "lng": 77.2090},
        "violations": active_violations[:10] 
    }

def generate_frames():
    global active_violations, is_emergency_active
    
    # Path to your video
    video_path = "traffic_video.mp4"
    cap = cv2.VideoCapture(video_path)
    
    if not cap.isOpened():
        print(f"CRITICAL ERROR: Could not open {video_path}. Check if the file is in the folder.")
        return

    while True:
        success, frame = cap.read()
        if not success:
            # Loop the video
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue

        # 1. Resize for Speed (Full HD display, but faster AI)
        frame = cv2.resize(frame, (1280, 720)) 

        # 2. Run Tracking
        try:
            # We use 'botsort.yaml' to avoid the 'lap' module error
            results = yolo_model.track(frame, persist=True, tracker="botsort.yaml")
            
            # 3. Basic Detection Logic
            found_emergency = False
            if results[0].boxes.id is not None:
                ids = results[0].boxes.id.cpu().numpy().astype(int)
                for obj_id in ids:
                    # Log new vehicles as violations for your project
                    if not any(v['plate'].endswith(str(obj_id)) for v in active_violations):
                        active_violations.insert(0, {
                            "type": "SPEEDING" if obj_id % 3 == 0 else "RULE BREAKER",
                            "time": time.strftime("%H:%M:%S"),
                            "plate": f"IND-TN-{obj_id:04d}"
                        })
            
            is_emergency_active = found_emergency
            
            # 4. Create the display image
            annotated_frame = results[0].plot()
            # Force Full HD 1080p for the web display
            display_frame = cv2.resize(annotated_frame, (1920, 1080))
            
            ret, buffer = cv2.imencode('.jpg', display_frame)
            if not ret:
                continue
            
            yield (b'--frame\r\n'
                   b'Content-Type: image/jpeg\r\n\r\n' + buffer.tobytes() + b'\r\n')
        
        except Exception as e:
            print(f"Tracking Error: {e}")
            break # Stop if AI crashes to avoid infinite error logs
@app.get("/video_feed")
async def video_feed():
    return StreamingResponse(generate_frames(), media_type="multipart/x-mixed-replace; boundary=frame")
# ===================== FRONTEND =====================

@app.get("/")
async def serve_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    return HTMLResponse("<h1>index.html not found</h1>")

# ===================== RUN =====================

if __name__ == "__main__":
    def open_browser():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8000")

    threading.Thread(target=open_browser, daemon=True).start()
    uvicorn.run(app, host="127.0.0.1", port=8000)

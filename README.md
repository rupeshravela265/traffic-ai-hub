# 🚦 Traffic.AI | Smart City Master Hub

Traffic.AI is a real-time traffic monitoring and emergency vehicle detection system. It uses **FastAPI** for the backend, **React** for the frontend dashboard, and **YOLOv8** for computer vision.

## ✨ Features
* **Real-time Detection:** Monitors vehicles, pedestrians, and traffic flow.
* **Emergency Priority:** Detects ambulances and police cars to trigger alerts.
* **Violation Tracking:** Logs speed or lane violations in an SQLite database.
* **Interactive Dashboard:** Live map integration and system health monitoring.

## 🚀 Quick Start
1. **Install dependencies:**
   `pip install -r requirements.txt`
2. **Run the app:**
   `python auth.py`
3. **View the dashboard:**
   Open `http://localhost:8000` in your browser.

## 🛠 Tech Stack
* **AI:** Ultralytics YOLOv8
* **Backend:** FastAPI (Python)
* **Frontend:** Tailwind CSS & React
* **Database:** SQLite3
# 💸 AI Smart Expense Scanner & Budget Coach

### Scan receipts. Auto-categorize. Chat with your finances — all in one place.

![Python](https://img.shields.io/badge/Python-3.10+-blue?style=flat-square)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square)
![Flask](https://img.shields.io/badge/Flask-3.x-black?style=flat-square)
![MongoDB](https://img.shields.io/badge/MongoDB-Atlas-green?style=flat-square)
![Groq](https://img.shields.io/badge/Groq-LLaMA3-red?style=flat-square)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

> **Gurjas Singh & Bhumik Chopra** — B.Tech CSE, Dronacharya College of Engineering, Gurugram University (2023–2027)

---

## 🎯 About The Project

Managing expenses manually is painful. This app solves that.

Take a photo of any receipt — the system reads it using OCR, extracts the total amount and date, classifies it into a spending category using a trained ML model, and stores it in the cloud. You can then open the AI chat and ask questions like *"How much did I spend on food this month?"* or *"What is my top expense category?"* and get instant answers.

Built as a college project but production-ready — deployed on Render with a React frontend, Flask backend, MongoDB Atlas database, and Groq-powered AI chat.

---

## ✨ Features

- 📸 **Receipt OCR** — Upload JPG, PNG, BMP, or PDF. EasyOCR extracts all text automatically with OpenCV preprocessing for better accuracy.
- 🏷️ **Auto-categorization** — A trained scikit-learn model (TF-IDF + LogisticRegression) classifies each expense into one of 6 categories instantly.
- 💬 **AI Budget Coach** — Groq LLaMA 3.3 70B powers a chat interface. Ask anything about your spending in plain English.
- 📊 **Visual Dashboard** — Donut charts, bar graphs, and monthly breakdowns built with Recharts.
- 🔐 **Secure Auth** — Clerk handles sign up, sign in, and session management.
- ☁️ **Cloud Storage** — All expense records stored and synced via MongoDB Atlas.
- 📷 **Webcam Support** — Capture receipts directly from webcam without uploading a file.
- 🚀 **Production Ready** — One-click deploy on Render via render.yaml.

---

## 🗂️ Project Structure

expense-scanner/
├── frontend/                   # React 19 + Vite + Clerk
│   ├── src/
│   │   ├── components/         # Dashboard, Charts, ExpenseTable, ChatBot
│   │   └── utils/api.js        # Axios API layer
│   └── vite.config.js
├── backend/                    # Flask REST API
│   ├── app.py                  # Main server — routes, OCR, Groq chat
│   ├── models.py               # MongoDB data models
│   └── requirements.txt
├── ocr_module/                 # Standalone ML pipeline
│   ├── src/
│   │   ├── production.py       # OCR + amount/date extraction
│   │   └── model.py            # Model training code
│   └── models/
│       ├── model.pkl
│       ├── vectorizer.pkl
│       └── encoder.pkl
├── render.yaml
└── .gitignore

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 19, Vite, Clerk Auth, Recharts |
| Backend | Flask, Python 3.10, PyMongo |
| AI Chat | Groq API — LLaMA 3.3 70B |
| OCR | EasyOCR, OpenCV, NumPy |
| ML Model | scikit-learn (TF-IDF + LogisticRegression) |
| Database | MongoDB Atlas |
| Auth | Clerk |
| Deployment | Render |

---

## 🧠 How the ML Pipeline Works
Receipt Image
│
▼
EasyOCR + OpenCV preprocessing
│
├──► TF-IDF Vectorizer ──► LogisticRegression ──► Category
│
├──► Regex + Priority rules ──► Total Amount (₹)
│
└──► Pattern matching ──► Date (YYYY-MM-DD)

**Categories:** Food & Dining · Healthcare · Shopping · Transport · Entertainment · Bills & Utilities

---

## ⚙️ Local Setup

### 1. Clone
git clone https://github.com/gurjas123456/expense-scanner-.git
cd expense-scanner-

### 2. Backend
cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
python app.py

Create backend/.env:
MONGODB_URI=your_mongodb_connection_string
MONGODB_DB_NAME=expense_db
OPENAI_API_KEY=gsk_your_groq_key

### 3. Frontend
cd frontend
npm install
npm run dev

Create frontend/.env:
VITE_API_BASE_URL=http://localhost:5000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_your_clerk_key

---

## ☁️ Deploy on Render

**Backend — Web Service**
- Root: `backend` · Build: `pip install -r requirements.txt` · Start: `gunicorn app:app`

**Frontend — Static Site**
- Root: `frontend` · Build: `npm install && npm run build` · Publish: `dist`

---

## 👨‍💻 Authors

| Name | Contribution |
|------|-------------|
| **Gurjas Singh** |  ML pipeline, OCR integration |
| **Bhumik Chopra** | Frontend development, UI/UX design, API integration |

---

## 📄 License

MIT — free to use, fork, and build on.

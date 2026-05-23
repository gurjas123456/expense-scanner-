💸 AI Smart Expense Scanner & Budget Coach
Scan receipts. Auto-categorize. Chat with your finances.

🎯 What is this?
A production-ready full-stack web app that turns a photo of any receipt into structured expense data — automatically. No manual entry, no spreadsheets.
Upload a receipt → OCR extracts the text → ML model categorizes it → Groq AI lets you chat with your spending data in plain English.

✨ Features
FeatureDescription📸 Receipt OCRUpload any receipt image — EasyOCR extracts all text🏷️ Auto-categorizationsklearn ML model classifies into 6 expense categories💬 AI Budget ChatAsk "What did I spend most on this month?" — powered by Groq LLaMA 3📊 Visual DashboardPie charts, bar graphs, monthly breakdowns🔐 AuthClerk-based sign up / sign in with session management☁️ Cloud StorageAll expenses stored in MongoDB Atlas🚀 DeployableOne-click deploy on Render via render.yaml

🗂️ Project Structure
expense-scanner/
├── frontend/                   # React 19 + Vite + Clerk
│   ├── src/
│   │   ├── components/         # Dashboard, Charts, ExpenseTable, Chat
│   │   └── utils/api.js        # Axios API layer
│   └── vite.config.js
│
├── backend/                    # Flask REST API
│   ├── app.py                  # Main server — routes, OCR, Groq chat
│   ├── models.py               # MongoDB data models
│   └── requirements.txt
│
├── ocr_module/                 # Standalone ML pipeline
│   ├── src/
│   │   ├── production.py       # OCR + amount/date extraction
│   │   └── model.py            # Model training code
│   └── models/                 # Saved .pkl files
│       ├── model.pkl
│       ├── vectorizer.pkl
│       └── encoder.pkl
│
├── assets/                     # Screenshots
│   ├── pic_1.jpeg
│   ├── pic_2.jpeg
│   └── pic_3.jpeg
│
├── render.yaml                 # Render deployment config
└── .gitignore

🛠️ Tech Stack
Frontend    →  React 19, Vite, Clerk Auth, Recharts
Backend     →  Flask, Python 3.10, PyMongo
AI / Chat   →  Groq API (LLaMA 3.3 70B)
OCR         →  EasyOCR, OpenCV, NumPy
ML Model    →  scikit-learn (TF-IDF + LogisticRegression)
Database    →  MongoDB Atlas
Auth        →  Clerk
Deploy      →  Render (backend as Web Service, frontend as Static Site)

⚙️ Local Setup
Prerequisites

Python 3.10+
Node.js 20+
MongoDB Atlas URI
Groq API key — free at console.groq.com
Clerk account — free at clerk.com

1. Clone
bashgit clone https://github.com/gurjas123456/expense-scanner-.git
cd expense-scanner-
2. Backend
bashcd backend
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
Create backend/.env:
envMONGODB_URI=your_mongodb_connection_string
MONGODB_DB_NAME=expense_db
OPENAI_API_KEY=gsk_your_groq_key
bashpython app.py
# Running on http://localhost:5000
3. Frontend
bashcd frontend
npm install
Create frontend/.env:
envVITE_API_BASE_URL=http://localhost:5000
VITE_CLERK_PUBLISHABLE_KEY=pk_test_your_clerk_key
bashnpm run dev
# Running on http://localhost:5173

☁️ Deploy on Render
Backend → Render Web Service

Root: backend/
Build: pip install -r requirements.txt
Start: gunicorn app:app

Frontend → Render Static Site

Root: frontend/
Build: npm install && npm run build
Publish: dist/


🧠 How the ML Pipeline Works
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
Categories: Food & Dining · Healthcare · Shopping · Transport · Entertainment · Bills & Utilities

👨‍💻 Authors
NameRoleGurjas SinghFull-stack dev, ML pipeline, OCR integrationBhumik ChopraFrontend, UI/UX, API integration
B.Tech Computer Science — Dronacharya College of Engineering, Gurugram University (2022–2026)

📄 License
MIT — free to use, fork, and build on.

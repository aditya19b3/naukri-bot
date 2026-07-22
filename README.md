# Naukri Auto-Apply Bot & Web UI

A modular, configurable Selenium bot that logs into [Naukri.com](https://www.naukri.com), searches for jobs by keyword/location, and auto-applies on your behalf. 

This project features a **FastAPI local backend** and a **Vite + React web application** designed to let you control the bot, manage configurations, and watch execution logs in real-time from your computer or **remotely from your mobile phone**.

---

## Key Features
- **Modern Dashboard UI**: Built with a sleek dark-theme and responsive grids (inspired by shadcn).
- **Mobile Friendly**: Deploy the static UI on Vercel and link it to your local PC via a tunnel (e.g. Ngrok) to start, stop, and monitor applications from your phone.
- **Enhanced AI Solver**: Uses OpenAI/Codex (or fallback heuristics) to answer conversational recruiter questions (CTC, experience, notice period, gender, shift flexibility, graduation year, work authorization, etc.).
- **Live Terminal Logging**: A simulated terminal pane that streams running bot logs in real-time.
- **Searchable Job History**: Interactive table displaying all processed jobs, company details, timestamps, and status badges.
- **Google Sheets Sync**: Optionally syncs all application results to a Google Sheet automatically.

---

## Project Structure
```
naukri-bot/
├── main.py               # CLI entry point for the automation bot
├── backend.py            # Local FastAPI server exposing the control REST API
├── config.py             # Configuration loader (reading from .env)
├── naukri_selectors.py   # CSS/XPath selectors for Naukri portal automation
├── ai_answerer.py        # OpenAI and rule-based questionnaire solver
├── apply.py              # Visite page & quick-apply drawer handler
├── requirements.txt      # Python dependencies
├── vercel.json           # Vercel static deployment configuration
├── frontend/             # React + Vite application folder
│   ├── index.html        # SPA entrypoint
│   ├── src/
│   │   ├── main.jsx      # Vite React startup
│   │   ├── App.jsx       # Control dashboard components and polling logic
│   │   └── index.css     # Dark-theme design system and Vanilla CSS layout
│   └── package.json
└── output/               # Results and logs folder (results.json / bot.log)
```

---

## 1. Local Prerequisites
- **Python 3.10+**
- **Node.js** (v18+) - only needed to run frontend locally
- **Google Chrome** installed on your computer
- **Ngrok** (or similar tunnel service) - only needed to access from mobile

---

## 2. Installation & Setup

### Step 1: Install Python Dependencies
```powershell
# Clone/download this repository and cd into it
cd naukri-bot

# Create a virtual environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# Install requirements
pip install -r requirements.txt
```

### Step 2: Configure Environment variables
1. Copy the example environment template:
   ```powershell
   copy .env.example .env       # Windows
   # cp .env.example .env       # macOS/Linux
   ```
2. Open `.env` and fill in your real values. This includes your Naukri email/password, OpenAI API key, and detailed profile settings (skills, notice period, gender, etc.) used by the AI questionnaire solver.

### Step 3: Install Frontend Dependencies
```powershell
cd frontend
npm install
cd ..
```

---

## 3. How to Run Locally

### Start the Backend Server (Local PC)
The backend FastAPI server orchestrates the selenium script, writes `.env` settings, and serves stats/logs.
```powershell
# Run the backend from the root directory
python backend.py
```
This runs the API on `http://127.0.0.1:8000`.

### Start the Frontend Client (Local PC)
In a separate terminal:
```powershell
cd frontend
npm run dev
```
Open `http://localhost:5173` in your browser. You can configure variables, press **Start Auto Apply** to trigger Chrome, and see real-time log outputs directly in your browser.

---

## 4. Mobile Controls & Vercel Deployment

To control your local bot from your mobile phone, we deploy the static React frontend on **Vercel** and connect it to your PC's backend through a secure **Ngrok** tunnel.

```
+-------------------+             +-----------------------+             +----------------------+
| Mobile Browser    |  HTTPS Req  | Public Tunnel URL     |  Port Fwd   | Local PC Backend     |
| (Vercel Frontend) | ----------> | (Ngrok Tunnel URL)    | ----------> | (FastAPI Port 8000)  |
+-------------------+             +-----------------------+             +----------------------+
```

### Step A: Start Ngrok on your PC
To allow Vercel to communicate with the FastAPI server running on your computer, expose it to the internet:
1. Install [Ngrok](https://ngrok.com/) on your PC and authenticate it.
2. Run this command in your command line:
   ```bash
   ngrok http 8000
   ```
3. Copy the generated **Forwarding URL** (looks like `https://xxxx-xxxx.ngrok-free.app`).

### Step B: Deploy Frontend to Vercel
1. Push your repository to **GitHub** (make sure `.env` and `output/` folders are ignored).
2. Go to the [Vercel Dashboard](https://vercel.com/) and click **Add New Project**.
3. Import your GitHub repository.
4. Vercel will automatically detect the settings in `vercel.json` and build the React app inside the `frontend/` directory.
5. Once deployed, open the Vercel URL on your mobile phone!

### Step C: Link Mobile to PC
1. Open the Vercel app URL in your mobile browser.
2. You will see "Local API Offline" in the header (since it's trying to connect to localhost by default).
3. Navigate to the **Bot Settings** tab.
4. Scroll to the bottom to **Connection Settings**.
5. Paste your copied **Ngrok URL** into the **Backend API URL Link** field and click **Save Configuration**.
6. The status in the header will turn green: **Live Bridge Active**. You are now linked to your computer!
7. Go to the **Control Panel** tab on your phone and tap **Run Auto Apply**. Chrome will launch on your computer, and logs will stream in real-time to your mobile screen.

---

## 5. Questionnaire AI Solver Details

When applying, recruiters often ask dynamic chatbot questions. The AI answering solver in `ai_answerer.py` evaluates questions using your profile context.

It supports:
- **Notice Period & Start Date**: Understands immediate joining, days, or months.
- **Relocation & Cities**: Evaluates matches against preferred and current locations.
- **Gender & Personal Info**: Handles multiple-choice gender selection.
- **Education & Degree**: Answers graduation year and degree type queries (e.g. B.Tech, MCA).
- **Work Authorization**: Selects matching work eligibility options.
- **CTC & Salary**: Safely inputs numeric CTC figures.
- **Experience Ratings**: Automatically answers numerical rating scales (e.g., rating a skill "9 out of 10").

If the OpenAI API is offline or key is missing, a **robust rule-based heuristic fallback solver** automatically takes over to ensure your applications do not get stuck.

---

## 6. Troubleshooting
- **API Offline**: Check if `backend.py` is running on your PC. If using mobile, ensure your Ngrok tunnel is still active (free tunnels expire/change URLs when restarted).
- **Chrome fails to launch**: Make sure Google Chrome is closed or configured properly. If Chrome is locked, check that headless mode isn't conflicting with existing open windows.
- **Login OTP / Captcha**: If Naukri presents a CAPTCHA, toggle `HEADLESS` to **false** in the settings, start the bot, and manually complete the challenge inside the Chrome browser that pops up.

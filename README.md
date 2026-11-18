# LinkedIn Job Apply Bot

## Folder Structure
```
linkedin_bot/
  linkedin_job_apply.py   <- main script
  resume.pdf              <- your default resume (uploaded when Groq unavailable)
  resume_tex/             <- LaTeX source of resume (used for local tailoring)
    main.tex
  requirements.txt        <- Python dependencies
  README.md               <- this file
  linkedin_resumes/       <- auto-created: tailored resumes saved here per job
  linkedin_chrome_profile/ <- auto-created: Chrome session (stays logged in)
```

## Setup on a New Machine (Personal Laptop)

### 1. Install Python 3.12
Download from https://www.python.org/downloads/

### 2. Install dependencies
```
pip install -r requirements.txt
```

### 3. Install ChromeDriver
- Check your Chrome version: Chrome menu → Help → About Google Chrome
- Download matching ChromeDriver from:
  https://googlechromelabs.github.io/chrome-for-testing/
- Extract `chromedriver.exe` to:
  `C:\Users\<YOU>\Downloads\chromedriver\chromedriver-win64\chromedriver.exe`
  (or update CHROMEDRIVER_PATH in the script)

### 4. Configure the script
Open `linkedin_job_apply.py` and update these lines at the top:
```python
CHROMEDRIVER_PATH = r"C:\path\to\chromedriver.exe"
RESUME_PATH       = r"C:\path\to\resume.pdf"
RESUME_TEX_PATH   = r"C:\path\to\resume_tex\main.tex"
RESUME_OUT_DIR    = r"C:\path\to\linkedin_resumes"
GROQ_API_KEY      = "gsk_..."   # from https://console.groq.com (free)
PHONE             = "91XXXXXXXXXX"
```

### 5. Run
```
# Test one job:
python linkedin_job_apply.py --debug-job https://www.linkedin.com/jobs/view/JOBID/

# Run all 20 jobs:
python linkedin_job_apply.py
```

## How it works
1. Opens Chrome with a saved profile (stays logged into LinkedIn)
2. Searches "Data Engineer" in Bengaluru, last 24h, Easy Apply
3. For each job:
   - Extracts title, company, JD from page
   - Tailors resume (Groq AI if available, else local keyword matching)
   - Clicks Easy Apply, fills all form steps automatically
   - Uploads tailored resume and submits
4. Stops when daily limit is reached

## Resume Tailoring
- **With Groq (personal network):** AI rewrites Summary + Skills to match JD → saves as DOCX
- **Without Groq (blocked network):** Local keyword matching reorders Skills section → saves as DOCX
- **Fallback:** Uses `resume.pdf` as-is

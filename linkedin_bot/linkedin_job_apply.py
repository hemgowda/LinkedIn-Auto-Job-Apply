"""
LinkedIn Job Auto-Apply Bot
- Finds jobs posted in last 24 hours
- Easy Apply: auto-submits
- External Apply: saves URL to a file for manual apply later
"""

import time, random, re, json, os
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    NoSuchElementException, TimeoutException,
    ElementClickInterceptedException, StaleElementReferenceException
)
try:
    from groq import Groq as _Groq
    _GROQ_AVAILABLE = True
except ImportError:
    _GROQ_AVAILABLE = False

# ── CONFIG ────────────────────────────────────────────────
LINKEDIN_EMAIL    = "hemanthgunduraj77@gmail.com"
LINKEDIN_PASSWORD = "NagarajAnitha@123"
JOB_KEYWORDS      = "Data Engineer"
JOB_LOCATION      = "Bengaluru"
MAX_JOBS          = 20
PHONE_NUMBER      = "6361613890"
RESUME_PATH       = r"C:\Users\AL09871\Downloads\Hemanthakumar_JN_Resume_Enhanced_1.pdf"
RESUME_TEX_PATH   = r"C:\Users\AL09871\Downloads\Hemanthakumar_JN_Resume_Enhanced_1\main.tex"
RESUME_OUT_DIR    = r"C:\Users\AL09871\Downloads\linkedin_resumes"   # tailored PDFs saved here
CHROMEDRIVER_PATH = r"C:\Users\AL09871\Downloads\chromedriver\chromedriver-win64\chromedriver.exe"
EXTERNAL_JOBS_LOG = r"C:\Users\AL09871\Downloads\external_jobs.txt"
MIN_DELAY, MAX_DELAY = 1, 2   # global between-job delay (reduced from 2–4)

# ── GROQ API — get free key at https://console.groq.com ───
GROQ_API_KEY = ""   # <-- paste your key here

# ── PROFILE — used to answer dynamic form questions ───────
PROFILE = {
    "first_name"        : "Hemanthakumar",
    "last_name"         : "J N",
    "full_name"         : "Hemanthakumar J N",
    "email"             : "hemanthgunduraj77@gmail.com",
    "phone"             : "6361613890",
    "linkedin_url"      : "https://www.linkedin.com/in/hemanthakumar-j-n",
    "city"              : "Bengaluru",
    "state"             : "Karnataka",
    "country"           : "India",
    "pincode"           : "560001",
    "total_experience"  : "5",          # years
    "current_ctc"       : "12",         # LPA (as asked in the form)
    "current_ctc_inr"   : "1200000",    # INR format fallback
    "expected_ctc"      : "18",         # LPA
    "expected_ctc_inr"  : "2300000",    # INR format fallback
    "notice_period"     : "30",         # days
    "notice_period_opt" : "15 Days",    # dropdown option text
    "current_company"   : "Elevance Health",
    "current_role"      : "Software Engineer II",
    "join_date"         : "2022/06",    # Year/Month joined current employer
    "highest_education" : "Bachelor",
    "degree"            : "B.E. Computer Science",
    "university"        : "VTU",
    "graduation_year"   : "2021",
    "cgpa"              : "8.5",
    "headline"          : "Data Engineer | Snowflake | Python | Spark | SQL | 5+ Years",
    "algo_trading_exp"  : "4",          # briefly exposed, not core algo trading
    "gender"            : "Male",
    "nationality"       : "Indian",
    "languages"         : "English",
    "visa_status"       : "Yes",
    "relocate"          : "Yes",
    "remote"            : "Yes",
    "authorized"        : "Yes",        # authorized to work
    "sponsor"           : "No",         # need sponsorship
    "disability"        : "No",
    "veteran"           : "No",
    "cover_letter"      : (
        "I am Hemanthakumar J N, a Data Engineer with 5+ years of experience "
        "building scalable data pipelines, ETL processes, and cloud-based data "
        "solutions using Snowflake, Python, Spark, and SQL. I have strong expertise "
        "in AEDL/EDL environments and data warehousing. I am excited about this "
        "opportunity and confident I can add immediate value to your team."
    ),
}
# ─────────────────────────────────────────────────────────

# ── AI ENGINE ─────────────────────────────────────────────
# Resume summary sent to Groq as context for every unknown question.
_RESUME_CONTEXT = """
Candidate: Hemanthakumar J N
Role: Data Engineer | 5+ years experience
Current Company: Elevance Health (US healthcare analytics)
Current Title: Software Engineer II
Skills: Python, SQL, Snowflake, Apache Spark, PySpark, DBT, Airflow,
        AWS (S3, Glue, Lambda, Redshift), Azure, GCP, Kafka (basic),
        ETL/ELT pipelines, data warehousing, AEDL/EDL, REST APIs,
        Git, CI/CD, Agile/Scrum
Education: B.E. Computer Science, VTU, 2021, CGPA 8.5
Location: Bengaluru, India
Notice period: 30 days (1 month)
Current CTC: 12 LPA | Expected CTC: 18 LPA
Willing to relocate: Yes | Open to remote: Yes
Work authorization: Authorized to work in India, no sponsorship needed

Domain exposure:
- Primarily enterprise data engineering (healthcare analytics, claims data)
- Briefly worked on financial/trading data pipelines as a data engineer
  (not a core quant/algo trader, but familiar with time-series data,
   market data ingestion, and low-latency data requirements)
- No direct HFT or strategy development experience

Key projects:
- Built end-to-end Snowflake data warehouse for claims processing (1B+ rows)
- Designed real-time Kafka → Spark → S3 pipeline for event data
- Automated ETL workflows with Airflow reducing manual effort by 60%
- Led migration of on-prem Oracle warehouse to cloud (Snowflake + AWS)
"""

_groq_client = None
_ai_cache: dict = {}   # cache answers to avoid repeated identical API calls


def _get_groq_client():
    global _groq_client
    if _groq_client is None and _GROQ_AVAILABLE and GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE":
        try:
            _groq_client = _Groq(api_key=GROQ_API_KEY)
        except Exception as e:
            print(f"    [AI] Groq init failed: {e}")
    return _groq_client


def ai_answer(question: str, field_type: str = "text",
              options: list = None) -> str:
    """Call Groq LLM to answer a job application question dynamically.

    Args:
        question:   The full question text from the form field.
        field_type: 'text', 'number', 'select', 'textarea', 'radio'
        options:    For dropdowns/radio — list of option strings to pick from.

    Returns:
        A string answer appropriate for the field type.
        Returns "" if AI is unavailable (falls back to static logic).
    """
    client = _get_groq_client()
    if client is None:
        return ""

    # Normalise cache key
    cache_key = f"{question}||{field_type}||{json.dumps(options or [])}"
    if cache_key in _ai_cache:
        return _ai_cache[cache_key]

    # Build the prompt
    if options:
        opts_str = "\n".join(f"  - {o}" for o in options)
        task = (
            f"The form has a dropdown/radio with these options:\n{opts_str}\n\n"
            f"Question: {question}\n\n"
            "Pick the SINGLE best option from the list above that honestly "
            "represents the candidate. Reply with ONLY the exact option text, "
            "nothing else."
        )
    elif field_type in ("number",):
        task = (
            f"Question: {question}\n\n"
            "Reply with ONLY a number (integer or decimal) that honestly "
            "represents the candidate. No units, no explanation, just the number."
        )
    elif field_type == "textarea":
        task = (
            f"Question: {question}\n\n"
            "Write a concise, professional answer (2-4 sentences max) that "
            "honestly represents the candidate for a job application form. "
            "Be specific and confident."
        )
    else:
        task = (
            f"Question: {question}\n\n"
            "Reply with a short, honest answer (1 word to 1 sentence) that "
            "represents the candidate for a job application form. "
            "No explanation needed."
        )

    system_prompt = (
        "You are filling out a job application form on behalf of this candidate. "
        "Always answer honestly based on the candidate's real background. "
        "Never fabricate experience the candidate does not have. "
        "If the candidate has partial/brief exposure, say so proportionally.\n\n"
        f"CANDIDATE PROFILE:\n{_RESUME_CONTEXT}"
    )

    try:
        response = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": task},
            ],
            temperature=0.2,
            max_tokens=120,
        )
        answer = response.choices[0].message.content.strip()
        answer = answer.strip('"\'')
        print(f"      [AI] → {answer[:60]}")
        _ai_cache[cache_key] = answer
        return answer
    except Exception as e:
        # Silent fallback — no error spam. Return sensible defaults by type.
        if options:
            return options[0]           # pick first option
        if field_type == "number":
            return "3"
        if field_type == "textarea":
            return (
                "I am a skilled Data Engineer with 3+ years of experience in "
                "building scalable data pipelines using Python, Spark, and SQL. "
                "I am excited about this opportunity and confident I can contribute "
                "meaningfully from day one."
            )
        return "Yes"


# ──────────────────────────────────────────────────────────

# ── RESUME GENERATION ─────────────────────────────────────────────────────────

def extract_jd(driver):
    """Extract job description by scrolling page and reading body text."""
    try:
        # Scroll down hard to trigger lazy load of job description
        for scroll_px in [600, 1200, 2000]:
            driver.execute_script(f"window.scrollBy(0, {scroll_px});")
            time.sleep(0.6)

        jd = driver.execute_script("""
            var body = document.body ? document.body.innerText : '';

            // Look for "About the job" section
            var markers = [
                'about the job',
                'job description',
                'key responsibilities',
                'about this role',
                'responsibilities',
                'requirements',
            ];
            var lower = body.toLowerCase();
            for (var i = 0; i < markers.length; i++) {
                var idx = lower.indexOf(markers[i]);
                if (idx !== -1) {
                    return body.substring(idx, idx + 4000);
                }
            }

            // No marker found — return everything after the first 800 chars (past nav/header)
            if (body.length > 800) return body.substring(800, 4800);
            return '';
        """) or ""

        # Scroll back to top so Easy Apply button is visible
        driver.execute_script("window.scrollTo(0, 0);")
        time.sleep(0.3)

        return jd[:4000]
    except Exception:
        return ""


def _find_pdflatex():
    """Find pdflatex executable on Windows."""
    import shutil
    # Check PATH first
    p = shutil.which("pdflatex")
    if p:
        return p
    # MiKTeX common install locations
    for base in [
        r"C:\Program Files\MiKTeX\miktex\bin\x64",
        r"C:\Program Files (x86)\MiKTeX\miktex\bin",
        r"C:\Users\AL09871\AppData\Local\Programs\MiKTeX\miktex\bin\x64",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\MiKTeX\miktex\bin\x64"),
    ]:
        exe = os.path.join(base, "pdflatex.exe")
        if os.path.exists(exe):
            return exe
    return None


def _groq_tailor_resume(jd_text):
    """Call Groq to get a tailored resume as plain text. Returns string or None."""
    if not _GROQ_AVAILABLE or not GROQ_API_KEY:
        return None
    try:
        with open(RESUME_TEX_PATH, "r", encoding="utf-8") as f:
            master_tex = f.read()
    except Exception:
        master_tex = ""

    prompt = f"""You are a professional resume writer. Given a job description and a candidate's current resume (in LaTeX), produce a tailored plain-text resume that:
1. Rewrites the Summary (2-3 sentences) to match the JD keywords and role
2. Reorders/adds Skills to highlight what the JD asks for
3. Keeps Experience, Projects, Education and Certifications exactly the same
4. Output ONLY the plain text resume content (no LaTeX, no markdown, no explanation)

JOB DESCRIPTION:
{jd_text[:1500]}

CANDIDATE RESUME (LaTeX source for reference):
{master_tex[:2000]}"""

    try:
        import httpx as _httpx
        http_client = _httpx.Client(verify=False)
        client = _Groq(api_key=GROQ_API_KEY, http_client=http_client)
        resp = client.chat.completions.create(
            model="llama3-8b-8192",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=2000,
            temperature=0.3,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"    [resume] Groq error: {e}")
        return None


def _build_docx_resume(text, out_path):
    """Write tailored resume text to a .docx file."""
    try:
        from docx import Document
        from docx.shared import Pt, Inches
        doc = Document()
        # Narrow margins
        for section in doc.sections:
            section.top_margin    = Inches(0.5)
            section.bottom_margin = Inches(0.5)
            section.left_margin   = Inches(0.6)
            section.right_margin  = Inches(0.6)
        for line in text.split("\n"):
            p = doc.add_paragraph(line)
            p.paragraph_format.space_after = Pt(2)
            for run in p.runs:
                run.font.size = Pt(10)
        doc.save(out_path)
        return True
    except Exception as e:
        print(f"    [resume] DOCX error: {e}")
        return False


def generate_tailored_resume(jd_text, job_id):
    """Use Groq to tailor resume to the JD.
    - If pdflatex available: LaTeX → PDF
    - Else: Groq plain text → DOCX
    - Falls back to RESUME_PATH on any failure."""
    if not jd_text or not GROQ_API_KEY:
        return RESUME_PATH

    os.makedirs(RESUME_OUT_DIR, exist_ok=True)

    # Return cached version if already generated
    for ext in [".pdf", ".docx"]:
        cached = os.path.join(RESUME_OUT_DIR, f"resume_{job_id}{ext}")
        if os.path.exists(cached):
            print(f"    [resume] Using cached: {os.path.basename(cached)}")
            return cached

    pdflatex = _find_pdflatex()

    # ── Path A: LaTeX → PDF ───────────────────────────────────────────────
    if pdflatex and os.path.exists(RESUME_TEX_PATH):
        with open(RESUME_TEX_PATH, "r", encoding="utf-8") as f:
            master_tex = f.read()
        latex_prompt = f"""You are a resume expert. Modify ONLY the Summary and Skills \\cvtag{{}} lines in this LaTeX resume to match the JD. Keep everything else identical. Output ONLY valid LaTeX code, no markdown fences.

JOB DESCRIPTION:
{jd_text[:1500]}

LATEX RESUME:
{master_tex}"""
        try:
            import httpx as _httpx
            http_client = _httpx.Client(verify=False)
            client = _Groq(api_key=GROQ_API_KEY, http_client=http_client)
            resp = client.chat.completions.create(
                model="llama3-8b-8192",
                messages=[{"role": "user", "content": latex_prompt}],
                max_tokens=4000, temperature=0.3,
            )
            new_tex = resp.choices[0].message.content.strip()
            if new_tex.startswith("```"):
                new_tex = re.sub(r"^```[a-z]*\n?", "", new_tex)
                new_tex = re.sub(r"\n?```$", "", new_tex)
            tex_file = os.path.join(RESUME_OUT_DIR, f"resume_{job_id}.tex")
            with open(tex_file, "w", encoding="utf-8") as f:
                f.write(new_tex)
            import subprocess
            out_pdf = os.path.join(RESUME_OUT_DIR, f"resume_{job_id}.pdf")
            for _ in range(2):
                subprocess.run([pdflatex, "-interaction=nonstopmode",
                                "-output-directory", RESUME_OUT_DIR, tex_file],
                               capture_output=True, timeout=60)
            if os.path.exists(out_pdf):
                print(f"    [resume] PDF ready: {os.path.basename(out_pdf)}")
                return out_pdf
        except Exception as e:
            print(f"    [resume] LaTeX path failed: {e}")

    # ── Path B: Groq plain text → DOCX ───────────────────────────────────
    text = _groq_tailor_resume(jd_text)
    if text:
        out_docx = os.path.join(RESUME_OUT_DIR, f"resume_{job_id}.docx")
        if _build_docx_resume(text, out_docx):
            print(f"    [resume] DOCX ready: {os.path.basename(out_docx)}")
            return out_docx

    # ── Path C: Local keyword tailoring — no network needed ──────────────
    local_docx = _local_tailor_resume_docx(jd_text, job_id)
    if local_docx:
        return local_docx

    print("    [resume] All methods failed — using default resume.")
    return RESUME_PATH


def _local_tailor_resume_docx(jd_text, job_id):
    """Keyword-based resume tailoring — zero network calls.
    Reads resume_tex/main.tex, scores each cvtag skill against JD keywords,
    puts best-matching skills first under a 'JD Match' heading, builds DOCX."""
    try:
        if not os.path.exists(RESUME_TEX_PATH):
            return None

        with open(RESUME_TEX_PATH, "r", encoding="utf-8", errors="replace") as f:
            tex = f.read()
        # Replace unicode symbols that cause cp1252 console errors
        tex = tex.replace('\u2192', '->').replace('\u2013', '-').replace('\u2014', '-')
        tex = tex.encode('ascii', errors='replace').decode('ascii').replace('?', ' ')

        # ── 1. Collect all unique skill tags ─────────────────────────────
        raw_tags = re.findall(r'\\cvtag\{([^}]+)\}', tex)
        seen, unique_tags = set(), []
        for t in raw_tags:
            tc = t.strip()
            if tc not in seen:
                seen.add(tc)
                unique_tags.append(tc)

        # ── 2. Score each tag against JD ─────────────────────────────────
        stop = {
            'and','the','for','are','with','that','this','from','have','will',
            'you','your','our','their','been','they','which','into','more',
            'also','other','some','such','each','both','about','than','then',
            'when','where','what','work','role','team','based','using','use',
            'used','full','time','min','level','industry','company','location',
            'type','skills','required','must','should','experience','years',
            'please','apply','data','provide','ensure','ability','strong',
        }
        jd_words = set(
            w.lower().strip('.,;:()[]')
            for w in re.split(r'\s+', jd_text)
            if len(w) >= 3 and w.lower().strip('.,;:()[]') not in stop
        )

        def score(tag):
            tl = tag.lower().replace('-', ' ').replace('/', ' ')
            return sum(1 for w in jd_words if w in tl or tl in w)

        matched = sorted([t for t in unique_tags if score(t) > 0],
                         key=score, reverse=True)
        rest    = [t for t in unique_tags if score(t) == 0]

        # ── 3. Build DOCX ────────────────────────────────────────────────
        from docx import Document
        from docx.shared import Pt, Inches
        from docx.enum.text import WD_ALIGN_PARAGRAPH
        from docx.oxml.ns import qn
        from docx.oxml import OxmlElement

        doc = Document()
        for sec in doc.sections:
            sec.top_margin    = Inches(0.4)
            sec.bottom_margin = Inches(0.4)
            sec.left_margin   = Inches(0.5)
            sec.right_margin  = Inches(0.5)

        def add_hr(p):
            pPr = p._p.get_or_add_pPr()
            pBdr = OxmlElement('w:pBdr')
            bot = OxmlElement('w:bottom')
            bot.set(qn('w:val'), 'single')
            bot.set(qn('w:sz'), '4')
            bot.set(qn('w:space'), '1')
            pBdr.append(bot)
            pPr.append(pBdr)

        def para(text, bold=False, size=9, center=False, space_before=0):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(space_before)
            p.paragraph_format.space_after  = Pt(1)
            if center:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            r = p.add_run(text)
            r.bold = bold
            r.font.size = Pt(size)
            return p

        def section_heading(title):
            p = para(title.upper(), bold=True, size=10, space_before=5)
            add_hr(p)

        # Header
        para("Hemanth Kumar J N", bold=True, size=14, center=True)
        email_m = re.search(r'\\href\{mailto:([^}]+)\}', tex)
        email = email_m.group(1) if email_m else "hemanthgunduraj77@gmail.com"
        para(f"{email}  |  +91-6361613890  |  Bengaluru, India  |  LinkedIn  |  GitHub",
             size=8, center=True)

        # Skills section — JD-matched first
        section_heading("Skills")
        if matched:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            r = p.add_run("JD Match:  ");  r.bold = True;  r.font.size = Pt(9)
            p.add_run("  |  ".join(matched[:18])).font.size = Pt(9)
        if rest:
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            r = p.add_run("Additional:  "); r.bold = True; r.font.size = Pt(9)
            p.add_run("  |  ".join(rest[:20])).font.size = Pt(9)

        # Remaining LaTeX sections (Experience, Education, Projects, etc.)
        parts = re.split(r'\\cvsection\{([^}]+)\}', tex)
        for i in range(1, len(parts), 2):
            sec_name = parts[i].strip()
            if "skill" in sec_name.lower():
                continue   # already added above

            sec_body = parts[i+1] if i+1 < len(parts) else ""
            # Clean LaTeX markup to plain text
            clean = re.sub(r'\\textbf\{([^}]+)\}',                   r'**\1**', sec_body)
            clean = re.sub(r'\\href\{[^}]+\}\{([^}]+)\}',            r'\1',     clean)
            clean = re.sub(r'\\cvtag\{[^}]+\}',                      '',        clean)
            clean = re.sub(r'\\[a-zA-Z]+(?:\[[^\]]*\])?\{([^}]*)\}', r'\1',     clean)
            clean = re.sub(r'\\[a-zA-Z]+\*?',                        '',        clean)
            clean = re.sub(r'[{}\\|]',                                '',        clean)
            clean = re.sub(r'\n{3,}',                                 '\n\n',    clean).strip()

            section_heading(sec_name)
            for ln in clean.split('\n'):
                ln = ln.strip()
                if not ln or len(ln) < 2:
                    continue
                is_bold = ln.startswith('**') and '**' in ln[2:]
                ln = ln.replace('**', '')
                p = doc.add_paragraph()
                p.paragraph_format.space_before = Pt(0)
                p.paragraph_format.space_after  = Pt(1)
                r = p.add_run(ln)
                r.bold = is_bold
                r.font.size = Pt(9)

        os.makedirs(RESUME_OUT_DIR, exist_ok=True)
        out_path = os.path.join(RESUME_OUT_DIR, f"resume_{job_id}.docx")
        doc.save(out_path)
        print(f"    [resume] Local tailor: {len(matched)} matched skills -> {os.path.basename(out_path)}")
        return out_path

    except Exception as e:
        print(f"    [resume] Local tailor error: {e}")
        return None


def pause(a=MIN_DELAY, b=MAX_DELAY):
    time.sleep(random.uniform(a, b))

def init_driver():
    # Use a dedicated Chrome profile folder for the script.
    # First run: Chrome opens, you log into LinkedIn once — session saved forever.
    # Every run after: already logged in, no verification needed.
    script_profile = r"C:\Users\AL09871\Downloads\linkedin_chrome_profile"
    os.makedirs(script_profile, exist_ok=True)

    opts = webdriver.ChromeOptions()
    opts.add_argument(f"--user-data-dir={script_profile}")
    opts.add_argument("--profile-directory=Default")
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)
    driver.set_page_load_timeout(60)
    driver.execute_script(
        "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
    return driver

def login(driver):
    print("[*] Checking LinkedIn session...")
    try:
        driver.get("https://www.linkedin.com/feed/")
    except Exception:
        driver.execute_script("window.stop();")
    pause(3, 4)

    # Already logged in via saved Chrome profile?
    if "feed" in driver.current_url or "mynetwork" in driver.current_url:
        print("[+] Already logged in via Chrome profile — no login needed.")
        return

    # Not logged in — try credentials
    print("[*] Not logged in. Trying credentials...")
    try:
        driver.get("https://www.linkedin.com/login")
        pause(3, 4)
        wait = WebDriverWait(driver, 15)
        ef = wait.until(EC.presence_of_element_located((By.ID, "username")))
        ef.clear(); ef.send_keys(LINKEDIN_EMAIL); pause(1, 2)
        pf = driver.find_element(By.ID, "password")
        pf.clear(); pf.send_keys(LINKEDIN_PASSWORD); pause(1, 2)
        driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
        pause(5, 7)
        if "feed" in driver.current_url or "mynetwork" in driver.current_url:
            print("[+] Logged in successfully.")
            return
    except TimeoutException:
        pass
    # Manual fallback (CAPTCHA / verification)
    print("[!] Please complete login manually in the Chrome window.")
    input("    Press ENTER after you are logged in...")

def _extract_job_ids(driver):
    """Extract all job IDs visible on the current page."""
    src   = driver.page_source
    found = set(re.findall(r'"jobPostingId["\s:]+(\d{8,})', src))
    found |= set(re.findall(r'/jobs/view/(\d{8,})/', src))
    found |= set(re.findall(r'data-job-id="(\d+)"', src))
    found |= set(re.findall(r'data-occludable-job-id="(\d+)"', src))
    found |= set(re.findall(r'"entityUrn":"urn:li:jobPosting:(\d+)"', src))
    found |= set(re.findall(r'jobPosting:(\d{8,})', src))
    found |= set(re.findall(r'"currentJobPostingId"\s*:\s*"?(\d{8,})"?', src))
    try:
        for a in driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']"):
            href = a.get_attribute("href") or ""
            m = re.search(r'/jobs/view/(\d{8,})/', href)
            if m:
                found.add(m.group(1))
    except Exception:
        pass
    return found


def _wait_for_job_cards(driver, timeout=10):
    """Wait until job cards are visible in the DOM. Returns True if found."""
    card_selectors = [
        "a[href*='/jobs/view/']",
        ".job-card-container",
        ".jobs-search-results__list-item",
        "[data-job-id]",
        "[data-occludable-job-id]",
    ]
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in card_selectors:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if els:
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def _load_search_page(driver, url):
    """Load a LinkedIn jobs search URL and wait for job cards to appear.
    Returns True if job cards were found."""
    try:
        driver.get(url)
    except Exception:
        driver.execute_script("window.stop();")

    wait_for_page(driver, timeout=12)
    dismiss_popups(driver)

    # Wait for actual job cards to render (JS-driven page)
    found = _wait_for_job_cards(driver, timeout=8)
    if not found:
        # Scroll once to trigger lazy load and try again
        driver.execute_script("window.scrollBy(0, 600)")
        pause(1, 1.5)
        found = _wait_for_job_cards(driver, timeout=5)
    return found


def _ensure_easy_apply_filter(driver):
    """Verify the Easy Apply filter chip is active; click it if not.
    Returns True if confirmed active after the call."""
    driver.execute_script("window.scrollTo(0, 0)")
    pause(0.4, 0.6)

    deadline = time.time() + 8
    while time.time() < deadline:
        try:
            for el in driver.find_elements(By.TAG_NAME, "button"):
                try:
                    if not el.is_displayed():
                        continue
                    inner = (driver.execute_script(
                        "return arguments[0].innerText||''", el) or "").strip().lower()
                    aria  = (el.get_attribute("aria-label") or "").lower()
                    if "easy apply" not in inner and "easy apply" not in aria:
                        continue
                    pressed = (el.get_attribute("aria-pressed") or "").lower()
                    if pressed == "true":
                        return True          # already active — good
                    # Not active — click it
                    driver.execute_script("arguments[0].click();", el)
                    pause(2, 2.5)
                    print("    [+] Clicked 'Easy Apply' filter chip.")
                    return True
                except Exception:
                    pass
        except Exception:
            pass
        time.sleep(0.4)
    return False   # chip not found


def collect_job_ids(driver):
    """Collect Easy Apply job IDs.
    Uses f_AL=true in URL from the start.  Waits properly for JS rendering.
    Falls back from 24h → 7 days if no results."""
    geo_id = "105214831"   # Bengaluru, Karnataka, India
    kw     = JOB_KEYWORDS.replace(' ', '%20')
    loc    = JOB_LOCATION.replace(' ', '%20')

    time_filters = [
        ("r86400",  "last 24 hours"),
        ("r604800", "last 7 days"),
    ]

    all_ids = []

    for tpr, tpr_label in time_filters:
        if len(all_ids) >= MAX_JOBS:
            break

        print(f"\n[*] Searching: {JOB_KEYWORDS} in {JOB_LOCATION} ({tpr_label}, Easy Apply)")
        page = 0

        # Load the search page ONCE — LinkedIn drops params on redirect,
        # so we load it, let it settle, then scroll the sidebar to get all jobs.
        url = (
            f"https://www.linkedin.com/jobs/search-results/"
            f"?keywords={kw}"
            f"&location={loc}"
            f"&f_TPR={tpr}"
            f"&f_AL=true"
            f"&sortBy=DD"
            f"&start=0"
        )
        print(f"[*] Loading: {url}")
        try:
            driver.execute_script("window.sessionStorage && window.sessionStorage.clear();")
        except Exception:
            pass
        try:
            driver.get(url)
        except Exception:
            driver.execute_script("window.stop();")
        wait_for_page(driver, timeout=12)
        dismiss_popups(driver)
        print(f"    [page] {driver.current_url[:100]}")

        if "authwall" in driver.current_url or "/login" in driver.current_url:
            print("    [!] Not logged in.")
            input("    Log in and press ENTER...")

        _wait_for_job_cards(driver, timeout=12)

        def _fetch_jobs_via_api(start_offset):
            """Use LinkedIn's Voyager API to fetch job IDs — returns pure JSON
            with all 25 jobs per page, no rendering needed."""
            import urllib.request, json as _json
            # Grab cookies from the browser session
            cookies = {c['name']: c['value'] for c in driver.get_cookies()}
            csrf    = cookies.get('JSESSIONID', '').strip('"')
            cookie_str = '; '.join(f"{k}={v}" for k, v in cookies.items())

            api_url = (
                "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
                f"?keywords={kw}&location={loc}&f_AL=true&f_TPR={tpr}"
                f"&sortBy=DD&start={start_offset}"
            )
            req = urllib.request.Request(api_url, headers={
                'User-Agent': driver.execute_script("return navigator.userAgent;"),
                'Cookie':     cookie_str,
                'Csrf-Token': csrf,
                'X-RestLi-Protocol-Version': '2.0.0',
                'Accept':     'application/json',
            })
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    body = resp.read().decode('utf-8', errors='ignore')
                ids = set(re.findall(r'(?:jobPosting:|/jobs/view/)(\d{8,})', body))
                ids |= set(re.findall(r'data-job-id="(\d{8,})"', body))
                ids |= set(re.findall(r'"jobId":(\d{8,})', body))
                return ids
            except Exception:
                return set()

        def _ids_from_rendered_page():
            """Wait for XHR to finish then scrape all IDs from the live DOM + source."""
            # Wait up to 5s for more than 1 job card to appear
            deadline = time.time() + 5
            while time.time() < deadline:
                cards = driver.find_elements(By.CSS_SELECTOR,
                    "[data-job-id], [data-occludable-job-id], a[href*='/jobs/view/']")
                if len(cards) > 2:
                    break
                time.sleep(0.3)

            ids = set()
            src = driver.page_source
            ids |= set(re.findall(r'jobPosting:(\d{8,})', src))
            ids |= set(re.findall(r'data-job-id="(\d{8,})"', src))
            ids |= set(re.findall(r'data-occludable-job-id="(\d{8,})"', src))
            ids |= set(re.findall(r'/jobs/view/(\d{8,})/', src))
            ids |= set(re.findall(r'"entityUrn":"urn:li:jobPosting:(\d{8,})"', src))
            for el in driver.find_elements(By.CSS_SELECTOR,
                    "[data-job-id], [data-occludable-job-id]"):
                jid = el.get_attribute("data-job-id") or \
                      el.get_attribute("data-occludable-job-id") or ""
                if re.match(r'\d{8,}', jid):
                    ids.add(jid)
            for a in driver.find_elements(By.CSS_SELECTOR, "a[href*='/jobs/view/']"):
                m = re.search(r'/jobs/view/(\d{8,})/', a.get_attribute("href") or "")
                if m:
                    ids.add(m.group(1))
            return ids

        print("    [*] Collecting job IDs...")
        start = 0
        while len(all_ids) < MAX_JOBS:
            # Try Voyager API first (fastest — returns all 25 at once)
            found = _fetch_jobs_via_api(start)
            if not found:
                # Fallback: read from rendered browser page
                found = _ids_from_rendered_page()

            new_ids = [i for i in found if i not in all_ids]
            print(f"    -> start={start}: +{len(new_ids)} IDs "
                  f"(total: {len(all_ids) + len(new_ids)})")

            if not new_ids:
                print("    -> No more jobs.")
                break

            all_ids.extend(new_ids)
            start += 25

            if start > 0 and len(new_ids) > 0:
                # Navigate browser to next page so cookies stay fresh
                next_url = (
                    f"https://www.linkedin.com/jobs/search-results/"
                    f"?keywords={kw}&location={loc}"
                    f"&f_TPR={tpr}&f_AL=true&sortBy=DD&start={start}"
                )
                try:
                    driver.get(next_url)
                except Exception:
                    driver.execute_script("window.stop();")
                pause(1.5, 2)

        print(f"    -> Total: {len(all_ids)} job IDs")
        if all_ids:
            break

    return all_ids[:MAX_JOBS]

def wait_for_page(driver, timeout=15):
    """Wait for page to fully load."""
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except Exception:
        pass


def _is_easy_apply_modal(el):
    """Return True if element is (or is inside) the Easy Apply form modal."""
    try:
        html = (el.get_attribute("innerHTML") or "").lower()
        outer = (el.get_attribute("outerHTML") or "").lower()
        return any(k in html + outer for k in [
            "easy-apply", "jobs-easy-apply", "easy apply",
            "apply to", "application", "job-apply",
        ])
    except Exception:
        return False


def handle_save_application_dialog(driver):
    """If LinkedIn shows 'Save this application?' — always click Save.
    Returns True if the dialog was found and handled."""
    try:
        for dialog in driver.find_elements(By.CSS_SELECTOR,
                                           "div[role='dialog'], dialog"):
            if not dialog.is_displayed():
                continue
            html = (dialog.get_attribute("innerHTML") or "").lower()
            if "save this application" not in html and "save to return" not in html:
                continue
            # Found the Save dialog — click Discard so Easy Apply stays open
            # (Save closes the modal; Discard keeps it open to continue)
            for btn in dialog.find_elements(By.TAG_NAME, "button"):
                try:
                    txt = (btn.text or "").strip().lower()
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    if "discard" in txt + aria:
                        driver.execute_script("arguments[0].click();", btn)
                        print("    [~] 'Save dialog' — clicked Discard to keep modal open.")
                        pause(0.5, 1)
                        return True
                except Exception:
                    pass
            # If no Discard button found, click Save as fallback
            for btn in dialog.find_elements(By.TAG_NAME, "button"):
                try:
                    txt = (btn.text or "").strip().lower()
                    if "save" in txt:
                        driver.execute_script("arguments[0].click();", btn)
                        print("    [~] 'Save dialog' — clicked Save (modal may close).")
                        pause(1, 2)
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    return False


class EasyApplyLimitReached(Exception):
    """Raised when LinkedIn shows the daily Easy Apply limit dialog."""
    pass


def check_easy_apply_limit(driver):
    """Raise EasyApplyLimitReached if LinkedIn's daily Easy Apply limit dialog is visible.
    Uses a very targeted check — only the specific limit dialog heading, not body text."""
    try:
        # Only check for the exact dialog heading element — avoids false positives
        hit = driver.execute_script("""
            // Look specifically for a dialog/modal containing the exact limit heading
            var dialogs = document.querySelectorAll(
                'div[role="dialog"], div[data-test-modal], .artdeco-modal');
            for (var i = 0; i < dialogs.length; i++) {
                var d = dialogs[i];
                if (!d.offsetParent) continue;  // not visible
                var inner = (d.innerText || d.textContent || '').toLowerCase();
                if (inner.indexOf("easy apply limit") !== -1
                        || inner.indexOf("reached today") !== -1) {
                    return true;
                }
            }
            return false;
        """)
        if hit:
            print("\n[!] Daily Easy Apply limit reached — stopping.")
            # Press Escape to close the dialog safely (avoids clicking wrong button)
            from selenium.webdriver.common.keys import Keys
            try:
                driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                time.sleep(0.5)
            except Exception:
                pass
            raise EasyApplyLimitReached("LinkedIn daily Easy Apply limit reached.")
    except EasyApplyLimitReached:
        raise
    except Exception:
        pass


def dismiss_popups(driver):
    """Dismiss sign-in prompts, Google auth banners, cookie notices.
    NEVER dismisses the Easy Apply form, Save dialog, or limit dialog."""

    # 0. Handle 'Save this application?' — always Save, never Discard
    handle_save_application_dialog(driver)

    dismissed = False

    # 1. LinkedIn auth-wall specific buttons (NOT the Easy Apply modal)
    authwall_selectors = [
        "button.authwall-join-form__form-toggle--bottom",
        ".authwall-join-form button[type='button']",
        # Cookie consent
        "button[action-type='ACCEPT']",
        "button#onetrust-accept-btn-handler",
    ]
    for sel in authwall_selectors:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            for el in els:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    dismissed = True
                    pause(0.5, 1)
        except Exception:
            pass

    # 2. Google one-tap sign-in overlay
    try:
        iframes = driver.find_elements(By.CSS_SELECTOR,
                                       "#credential_picker_container iframe")
        for iframe in iframes:
            if iframe.is_displayed():
                driver.switch_to.frame(iframe)
                try:
                    close_btn = driver.find_element(By.ID, "close_button")
                    close_btn.click()
                    dismissed = True
                    pause(0.5, 1)
                except Exception:
                    pass
                finally:
                    driver.switch_to.default_content()
    except Exception:
        pass

    # 3. Any visible modal/dialog that is NOT the Easy Apply modal
    try:
        for dialog in driver.find_elements(By.CSS_SELECTOR,
                                           "div[role='dialog'], dialog"):
            if not dialog.is_displayed():
                continue
            # Skip Easy Apply modal — never touch it here
            if _is_easy_apply_modal(dialog):
                continue
            # Skip "Save this application?" — handled above
            html = (dialog.get_attribute("innerHTML") or "").lower()
            if "save this application" in html or "save to return" in html:
                continue
            # NEVER dismiss the Easy Apply limit dialog here — let check_easy_apply_limit handle it
            if ("easy apply limit" in html or "reached today" in html
                    or "you reached today" in html):
                continue
            # Try to close other overlays (sign-in banners, etc.)
            for btn in dialog.find_elements(By.TAG_NAME, "button"):
                try:
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    txt  = (btn.text or "").lower()
                    combined = aria + " " + txt
                    # Removed "got it" — that belongs to the limit dialog
                    if any(k in combined for k in
                           ["dismiss", "close", "skip", "not now",
                            "no thanks", "maybe later"]):
                        driver.execute_script("arguments[0].click();", btn)
                        dismissed = True
                        pause(0.5, 1)
                        break
                except Exception:
                    pass
    except Exception:
        pass

def get_text(driver, selectors, timeout=6):
    """Return first non-empty text from a list of CSS selectors."""
    for sel in selectors:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, sel))
            )
            t = el.text.strip()
            if t:
                return t
        except Exception:
            pass
    # Fallback: try page source regex for title
    return ""

def get_job_info(driver):
    """Extract title and company from current job page."""
    import json as _json
    title, company = "", ""

    # Fastest: browser tab title format is "Job Title | Company | LinkedIn"
    # (pipe-separated, NOT dash-separated)
    try:
        page_title = driver.title or ""
        if " | LinkedIn" in page_title:
            parts = [p.strip() for p in page_title.replace(" | LinkedIn", "").split(" | ")]
            if len(parts) >= 2:
                title   = parts[0]
                company = parts[1]
            elif len(parts) == 1 and parts[0]:
                title = parts[0]
    except Exception:
        pass

    if title and company:
        return title, company

    # Poll up to 10s for the job top-card to fully render
    # LinkedIn loads job detail via XHR — DOM is empty right after navigation
    for _ in range(20):
        try:
            raw = driver.execute_script("""
                function gt(el) {
                    return el ? (el.innerText||el.textContent||'').replace(/\\s+/g,' ').trim() : '';
                }
                var title = '', company = '';

                // Title: first h1 on the page
                var h1 = document.querySelector('h1');
                if (h1) title = gt(h1);

                // Company: try every likely selector
                var cSels = [
                    // 2024-25 unified top card
                    '.job-details-jobs-unified-top-card__company-name',
                    '.jobs-unified-top-card__company-name',
                    // Any element whose class contains "company-name"
                    '[class*="company-name"]',
                    // The subtitle line just below h1 (first anchor or first div)
                    '.job-details-jobs-unified-top-card__primary-description-container a',
                    '.job-details-jobs-unified-top-card__primary-description a',
                    // Fallback: second line of top card
                    '.jobs-unified-top-card__subtitle-primary-grouping a',
                    'a[data-tracking-control-name*="company"]',
                ];
                for (var i=0; i<cSels.length; i++) {
                    var el = document.querySelector(cSels[i]);
                    var v = el ? gt(el) : '';
                    if (v && v.length > 1) { company = v; break; }
                }

                // If company still empty, try the subtitle span right after h1
                if (!company) {
                    var spans = document.querySelectorAll(
                        '.job-details-jobs-unified-top-card__primary-description span,' +
                        '.jobs-unified-top-card__company-name span');
                    for (var j=0; j<spans.length; j++) {
                        var sv = gt(spans[j]);
                        if (sv && sv.length > 1 && sv.indexOf('·') === -1) {
                            company = sv; break;
                        }
                    }
                }

                return JSON.stringify({title: title, company: company});
            """) or "{}"
            data   = _json.loads(raw)
            title   = data.get("title",   "").strip()
            company = data.get("company", "").strip()
            if title and company:
                break   # both found — stop polling
            if title or company:
                time.sleep(0.3)   # partial — wait a bit more
            else:
                time.sleep(0.5)   # nothing yet — wait longer
        except Exception:
            time.sleep(0.5)

    # Debug: show what's actually visible if still empty
    if not title or not company:
        try:
            dump = driver.execute_script("""
                var h1s = Array.from(document.querySelectorAll('h1'))
                    .map(function(e){return (e.innerText||'').trim();})
                    .filter(function(t){return t;});
                var src_snippet = document.documentElement.innerHTML.substring(0,500);
                return JSON.stringify({h1s: h1s, url: location.href, snippet: src_snippet});
            """)
            print(f"    [dbg] {dump[:300]}")
        except Exception as e:
            print(f"    [dbg] JS error: {e}")

    # Last resort: page source regex (works for Voyager JSON embedded in HTML)
    if not title or not company:
        src = driver.page_source
        if not title:
            for pat in [
                r'"jobPostingTitle"\s*:\s*"([^"\\]{3,150})"',
                r'"title"\s*:\s*"([^"\\]{3,150})"',
                r'"jobTitle"\s*:\s*"([^"\\]{3,150})"',
            ]:
                m = re.search(pat, src)
                if m: title = m.group(1).strip(); break
        if not company:
            for pat in [
                r'"companyName"\s*:\s*"([^"\\]{2,100})"',
                r'"hiringOrganization"\s*:\s*\{[^}]{0,300}"name"\s*:\s*"([^"\\]{2,100})"',
            ]:
                m = re.search(pat, src)
                if m: company = m.group(1).strip(); break

    return title or "Unknown Title", company or "Unknown Company"

def is_already_applied(driver):
    """Return True only if LinkedIn confirms the job is FULLY submitted.
    Does NOT return True for saved/partial applications — those show 'Continue'."""
    try:
        src = driver.page_source
        # JSON flags that only appear after full submission
        if '"applied":true' in src or '"alreadyApplied":true' in src:
            return True
        # CSS badge that appears only after submission (not on saved drafts)
        for sel in [
            ".jobs-apply-button--applied",
            "[class*='applied-badge']",
        ]:
            try:
                els = driver.find_elements(By.CSS_SELECTOR, sel)
                if any(e.is_displayed() for e in els):
                    return True
            except Exception:
                pass
        # Visible text signals — only after full submission
        for xpath in [
            "//*[contains(text(),'You applied')]",
            "//*[contains(text(),'application was sent')]",
            "//*[contains(text(),'Applied on')]",
        ]:
            try:
                el = driver.find_element(By.XPATH, xpath)
                if el.is_displayed():
                    return True
            except Exception:
                pass
    except Exception:
        pass
    return False


def find_apply_btn(driver, debug=False):
    """
    Find the apply/continue button — returns (btn, is_easy_apply).
    Handles:
      1. 'Easy Apply' button  → fresh application
      2. 'Continue' button    → saved/partial application
      3. External 'Apply'     → external link
    Returns (None, None) if already fully applied or button not found.
    Pass debug=True to print all visible buttons for diagnosis.
    """
    if is_already_applied(driver):
        return None, None

    try:
        continue_btn = None
        all_visible  = []  # collect for debug

        for btn in driver.find_elements(By.TAG_NAME, "button"):
            try:
                if not btn.is_displayed():
                    continue
                label = (btn.get_attribute("aria-label") or "").lower()
                text  = (btn.text or "").strip().lower()
                # Also read innerText via JS — catches buttons with nested spans
                inner = ""
                try:
                    inner = (driver.execute_script(
                        "return arguments[0].innerText||''", btn) or "").strip().lower()
                except Exception:
                    pass
                combined = text + " " + label + " " + inner
                all_visible.append((text, label, inner))

                if "easy apply" in combined:
                    return btn, True
                if "submit application" in combined:
                    # Already at review/submit stage — treat as Easy Apply
                    return btn, True
                if "continue" in combined:
                    continue_btn = btn
            except StaleElementReferenceException:
                pass

        if continue_btn is not None:
            print("    -> Found 'Continue' button — resuming saved application...")
            return continue_btn, True

        # Check anchor tags — Easy Apply, Continue (saved app), external Apply
        for a in driver.find_elements(By.TAG_NAME, "a"):
            try:
                if not a.is_displayed():
                    continue
                label = (a.get_attribute("aria-label") or "").lower()
                text  = (a.text or "").strip().lower()
                href  = (a.get_attribute("href") or "")
                inner = ""
                try:
                    inner = (driver.execute_script(
                        "return arguments[0].innerText||''", a) or "").strip().lower()
                except Exception:
                    pass
                combined = text + " " + label + " " + inner
                if "easy apply" in combined:
                    return a, True
                # Continue link (saved/partial application) — href contains job view URL
                if "continue" in combined and "linkedin.com/jobs/view/" in href:
                    print("    -> Found 'Continue' link (saved application) — resuming...")
                    return a, True
                if text == "apply" and "linkedin.com" not in href:
                    return a, False
            except StaleElementReferenceException:
                pass

        # Fallback: any button with text "Apply"
        for btn in driver.find_elements(By.TAG_NAME, "button"):
            try:
                if btn.is_displayed() and (btn.text or "").strip().lower() == "apply":
                    return btn, False
            except Exception:
                pass

        # Debug dump — always print on failure so we can see what's there
        if all_visible:
            print("    [DEBUG] Visible buttons on page (none matched):")
            for txt, aria, inner in all_visible:
                if txt or aria or inner:
                    print(f"      text={repr(txt)}  aria={repr(aria)}  inner={repr(inner[:60])}")
        else:
            print("    [DEBUG] No visible buttons found on page at all.")

    except Exception:
        pass
    return None, None

def get_field_hint(driver, element):
    """Extract label + placeholder + aria-label text to understand what a field is asking."""
    hint = ""
    try:
        el_id = element.get_attribute("id") or ""
        if el_id:
            try:
                hint += driver.find_element(By.CSS_SELECTOR, f"label[for='{el_id}']").text + " "
            except Exception:
                pass
        hint += (driver.execute_script("""
            var el = arguments[0];
            var parent = el.closest('fieldset,li,div[class*="field"],div[class*="form-group"],div[class*="form"]');
            if (!parent) parent = el.parentElement;
            if (parent) {
                var lbl = parent.querySelector('label,legend,span[class*="label"],div[class*="label"]');
                return lbl ? lbl.innerText : '';
            }
            return '';
        """, element) or "") + " "
        hint += (element.get_attribute("placeholder") or "") + " "
        hint += (element.get_attribute("aria-label") or "") + " "
    except Exception:
        pass
    return hint.lower().strip()


def smart_answer(hint, itype="text"):
    """Return the best profile answer for a field based on its hint text."""
    h = hint
    # ── Identity ──────────────────────────────────────────────────────────
    if any(k in h for k in ["first name", "firstname"]):           return PROFILE["first_name"]
    if any(k in h for k in ["last name", "lastname", "surname"]):  return PROFILE["last_name"]
    if any(k in h for k in ["full name", "fullname"]):             return PROFILE["full_name"]
    if "middle name" in h:                                          return ""
    if "email" in h:                                                return PROFILE["email"]
    if any(k in h for k in ["mobile", "phone"]) or itype == "tel": return PROFILE["phone"]
    # ── Location ──────────────────────────────────────────────────────────
    if any(k in h for k in ["city", "location"]):                  return PROFILE["city"]
    if "state" in h:                                                return PROFILE["state"]
    if "country" in h:                                              return PROFILE["country"]
    if any(k in h for k in ["pin", "zip", "postal"]):              return PROFILE["pincode"]
    # ── Online presence ───────────────────────────────────────────────────
    if "linkedin" in h:                                             return PROFILE["linkedin_url"]
    if any(k in h for k in ["github", "portfolio", "website"]):    return PROFILE["linkedin_url"]
    # ── Personal ──────────────────────────────────────────────────────────
    if "gender" in h:                                               return PROFILE["gender"]
    if "nation" in h:                                               return PROFILE["nationality"]
    if "language" in h:                                             return PROFILE["languages"]
    # ── Headline / Summary ────────────────────────────────────────────────
    if any(k in h for k in ["headline", "professional headline",
                              "profile headline"]):                  return PROFILE["headline"]
    if any(k in h for k in ["summary", "about", "bio"]):           return PROFILE["cover_letter"]
    # ── Education ─────────────────────────────────────────────────────────
    if any(k in h for k in ["degree", "qualification"]):           return PROFILE["degree"]
    if any(k in h for k in ["university", "college", "institution",
                              "ug", "pg", "school"]):               return PROFILE["university"]
    if any(k in h for k in ["graduation year", "pass out", "passout",
                              "completion year", "year of passing",
                              "ug / pg", "ug/pg completion"]):      return PROFILE["graduation_year"]
    if any(k in h for k in ["cgpa", "gpa", "percentage", "marks"]): return PROFILE["cgpa"]
    # ── Experience ────────────────────────────────────────────────────────
    if any(k in h for k in ["total exp", "years of exp", "year of exp",
                              "how many year", "experience in year",
                              "years experience", "work experience",
                              "total work"]):                        return PROFILE["total_experience"]
    if any(k in h for k in ["electronic trading", "algorithmic trading",
                              "algo trading", "quant", "hft"]):     return PROFILE["algo_trading_exp"]
    # ── Current employer ──────────────────────────────────────────────────
    if any(k in h for k in ["current company", "current employer",
                              "name of your current employer",
                              "employer"]):                          return PROFILE["current_company"]
    if any(k in h for k in ["current role", "current title",
                              "designation", "job title"]):          return PROFILE["current_role"]
    if any(k in h for k in ["when did you join", "join date",
                              "joining date", "year/month",
                              "year / month"]):                      return PROFILE["join_date"]
    # ── Compensation ──────────────────────────────────────────────────────
    if any(k in h for k in ["current ctc", "current salary",
                              "current comp", "current lpa",
                              "ctc in lpa"]):
        # Return LPA if question mentions LPA, else INR
        return PROFILE["current_ctc"] if "lpa" in h else PROFILE["current_ctc_inr"]
    if any(k in h for k in ["expected ctc", "expected salary",
                              "expected comp", "salary expect",
                              "expected lpa"]):
        return PROFILE["expected_ctc"] if "lpa" in h else PROFILE["expected_ctc_inr"]
    if any(k in h for k in ["salary", "ctc", "compensation", "package"]):
        return PROFILE["expected_ctc"]
    # ── Notice / joining ──────────────────────────────────────────────────
    if any(k in h for k in ["notice period", "notice"]):
        # Dropdown options often say "1 month", "30 days" etc.
        return PROFILE["notice_period_opt"] if itype == "select" else PROFILE["notice_period"]
    if any(k in h for k in ["how soon", "join bestex", "earliest join",
                              "when can you join", "available to join"]):
        return PROFILE["notice_period_opt"]
    # ── Work preferences ──────────────────────────────────────────────────
    if any(k in h for k in ["relocat", "willing to move"]):        return PROFILE["relocate"]
    if any(k in h for k in ["remote", "work from home"]):          return PROFILE["remote"]
    if any(k in h for k in ["authoriz", "legally eligible",
                              "eligible to work"]):                  return PROFILE["authorized"]
    if any(k in h for k in ["sponsor", "visa sponsor"]):           return PROFILE["sponsor"]
    if any(k in h for k in ["disability", "disabled"]):            return PROFILE["disability"]
    if any(k in h for k in ["veteran", "military"]):               return PROFILE["veteran"]
    # ── Generic numeric / year fallback ───────────────────────────────────
    if itype == "number":                                           return "3"
    if any(k in h for k in ["year", "exp"]):                       return "3"
    # ── Unknown field — signal caller to use AI ───────────────────────────
    return None   # None = "I don't know, use AI"


def _get_label_for_field(driver, element):
    """Return the full visible question/label text for a form element.
    Wider search than get_field_hint — returns original case for AI prompts."""
    parts = []
    try:
        el_id = element.get_attribute("id") or ""
        if el_id:
            try:
                parts.append(
                    driver.find_element(By.CSS_SELECTOR,
                                        f"label[for='{el_id}']").text.strip())
            except Exception:
                pass
        js_label = driver.execute_script("""
            var el = arguments[0];
            // Walk up to find a fieldset, li, or form-group ancestor
            var parent = el.closest(
                'fieldset, li, div[class*="field"], div[class*="form-group"],'
                'div[class*="form"], div[class*="question"]'
            );
            if (!parent) parent = el.parentElement && el.parentElement.parentElement;
            if (parent) {
                var lbl = parent.querySelector(
                    'label, legend, span[class*="label"], div[class*="label"],'
                    'p, h3, h4'
                );
                return lbl ? lbl.innerText.trim() : '';
            }
            return '';
        """, element)
        if js_label:
            parts.append(js_label.strip())
        ph = element.get_attribute("placeholder") or ""
        if ph:
            parts.append(ph.strip())
        aria = element.get_attribute("aria-label") or ""
        if aria:
            parts.append(aria.strip())
    except Exception:
        pass
    # Return longest/most informative part
    parts = [p for p in parts if p]
    return max(parts, key=len) if parts else ""


def _fill_typeahead(driver, inp, answer):
    """Fill a typeahead/autocomplete input and pick the FIRST suggestion.
    Used for location fields where typing triggers a dropdown list.
    Returns True if a suggestion was selected, False otherwise."""
    try:
        inp.clear()
        pause(0.3, 0.5)
        inp.send_keys(answer)
        # Wait up to 4s for a suggestion dropdown to appear
        suggestion_selectors = [
            # LinkedIn typeahead list items
            ".basic-typeahead__selectable",
            ".search-basic-typeahead__selectable",
            "[class*='typeahead'] li",
            "[class*='typeahead'] [role='option']",
            "[role='listbox'] [role='option']",
            "[role='listbox'] li",
            # Generic autocomplete
            ".autocomplete-results li",
            "ul[role='listbox'] li",
        ]
        deadline = time.time() + 4
        while time.time() < deadline:
            for sel in suggestion_selectors:
                try:
                    items = driver.find_elements(By.CSS_SELECTOR, sel)
                    visible = [i for i in items if i.is_displayed()]
                    if visible:
                        # Click the first visible suggestion
                        driver.execute_script("arguments[0].click();", visible[0])
                        pause(0.3, 0.5)
                        return True
                except Exception:
                    pass
            time.sleep(0.3)
        # No suggestion appeared — just press Enter/Tab to confirm typed value
        inp.send_keys(Keys.RETURN)
        return False
    except Exception:
        return False


def _is_typeahead_field(inp):
    """Return True if this input is a typeahead/autocomplete field."""
    try:
        role      = (inp.get_attribute("role") or "").lower()
        autocomplete = (inp.get_attribute("autocomplete") or "").lower()
        aria_auto = (inp.get_attribute("aria-autocomplete") or "").lower()
        list_attr = inp.get_attribute("list")          # datalist
        # LinkedIn uses role="combobox" for typeaheads
        return (role == "combobox" or aria_auto in ("list", "both")
                or list_attr is not None)
    except Exception:
        return False


def fill_form_fields(driver, resume_path=None):
    """Dynamically read every visible field, determine what it's asking,
    and fill it. Uses static lookup first; falls back to Groq AI for
    any question not covered by keyword matching."""
    pause(0.4, 0.6)
    _resume = resume_path or RESUME_PATH

    # ── Resume selection / upload ──────────────────────────────────────────
    # LinkedIn shows either:
    # A) Radio buttons listing previously uploaded resumes → select the first one
    # B) Hidden input[type=file] → send_keys the path directly
    # C) "Upload resume" visible button → click it, then send_keys to the hidden input
    try:
        # Case A: radio buttons for existing resumes — select the first one (most recent)
        resume_radios = driver.find_elements(By.CSS_SELECTOR,
            "input[type='radio'][name*='resume'], "
            "input[type='radio'][id*='resume'], "
            "[class*='resume'] input[type='radio']")
        visible_radios = [r for r in resume_radios if r.is_displayed() or True]
        if visible_radios:
            # Pick the first radio (most recently uploaded resume)
            first = visible_radios[0]
            if not first.is_selected():
                driver.execute_script("arguments[0].click();", first)
                pause(0.3, 0.5)
        else:
            # Case B: hidden file input — send path directly
            file_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            uploaded = False
            for fi in file_inputs:
                try:
                    fi.send_keys(_resume)
                    pause(1, 1.5)
                    uploaded = True
                    break
                except Exception:
                    pass

            # Case C: "Upload resume" visible button → click to reveal file input
            if not uploaded and _resume and os.path.exists(_resume):
                for btn in driver.find_elements(By.TAG_NAME, "button"):
                    try:
                        label = ((btn.text or "") + " " +
                                 (btn.get_attribute("aria-label") or "")).lower()
                        if "upload resume" in label or "upload a resume" in label:
                            driver.execute_script("arguments[0].click();", btn)
                            pause(0.5, 1)
                            # Now find the newly revealed file input
                            for fi in driver.find_elements(
                                    By.CSS_SELECTOR, "input[type='file']"):
                                try:
                                    fi.send_keys(_resume)
                                    pause(1, 1.5)
                                    break
                                except Exception:
                                    pass
                            break
                    except Exception:
                        pass
    except Exception:
        pass

    # ── Text / number / tel / email inputs ───────────────────────────────
    try:
        for inp in driver.find_elements(By.CSS_SELECTOR,
            "input:not([type='file']):not([type='radio']):not([type='checkbox'])"
            ":not([type='hidden']):not([type='submit']):not([type='button'])"):
            try:
                if not inp.is_displayed():
                    continue
                if (inp.get_attribute("value") or "").strip():
                    continue  # already filled
                itype  = (inp.get_attribute("type") or "text").lower()
                hint   = get_field_hint(driver, inp)
                answer = smart_answer(hint, itype)
                if answer is None:
                    question = _get_label_for_field(driver, inp)
                    answer = ai_answer(question or hint, field_type=itype) or "Yes"
                if answer:
                    # Typeahead fields (location etc.) need special handling
                    if _is_typeahead_field(inp):
                        _fill_typeahead(driver, inp, answer)
                    else:
                        inp.clear()
                        inp.send_keys(answer)
            except Exception:
                pass
    except Exception:
        pass

    # ── Textareas (cover letter, free-text questions) ─────────────────────
    try:
        for ta in driver.find_elements(By.TAG_NAME, "textarea"):
            try:
                if not ta.is_displayed():
                    continue
                if (ta.get_attribute("value") or "").strip():
                    continue  # already filled
                hint     = get_field_hint(driver, ta)
                question = _get_label_for_field(driver, ta)
                # If the label mentions "cover letter", use static cover letter
                if any(k in hint for k in ["cover letter", "cover_letter"]):
                    ta.clear()
                    ta.send_keys(PROFILE["cover_letter"])
                else:
                    # Any other free-text question → AI
                    answer = ai_answer(question or hint,
                                       field_type="textarea") or PROFILE["cover_letter"]
                    ta.clear()
                    ta.send_keys(answer)
            except Exception:
                pass
    except Exception:
        pass

    # ── Select dropdowns ──────────────────────────────────────────────────
    try:
        for sel_el in driver.find_elements(By.TAG_NAME, "select"):
            try:
                if not sel_el.is_displayed():
                    continue
                s   = Select(sel_el)
                cur = (s.first_selected_option.get_attribute("value") or "").strip()
                if cur in ["", "Select an option", "Please select", "-1", "0"]:
                    hint     = get_field_hint(driver, sel_el)
                    question = _get_label_for_field(driver, sel_el)
                    # Collect valid options for matching
                    valid_opts = [
                        opt.text.strip() for opt in s.options
                        if (opt.get_attribute("value") or "").strip()
                        not in ["", "Select an option", "Please select", "-1"]
                    ]

                    answer = smart_answer(hint, itype="select")
                    if answer is None:
                        # Ask AI — give it the full option list to pick from
                        answer = ai_answer(question or hint,
                                           field_type="select",
                                           options=valid_opts)

                    answer_l = (answer or "").lower()
                    matched  = False
                    # Try to match AI/static answer against option text
                    for opt_text in valid_opts:
                        if answer_l in opt_text.lower() or opt_text.lower() in answer_l:
                            s.select_by_visible_text(opt_text)
                            matched = True
                            break
                    # If AI returned the exact option text
                    if not matched and answer in valid_opts:
                        s.select_by_visible_text(answer)
                        matched = True
                    # Last resort: pick first valid option
                    if not matched and valid_opts:
                        s.select_by_visible_text(valid_opts[0])
            except Exception:
                pass
    except Exception:
        pass

    # ── Radio buttons ─────────────────────────────────────────────────────
    try:
        seen = set()
        for r in driver.find_elements(By.CSS_SELECTOR, "input[type='radio']"):
            try:
                name = r.get_attribute("name")
                if not name or name in seen:
                    continue
                if r.is_selected():
                    seen.add(name)
                    continue
                group    = driver.find_elements(By.CSS_SELECTOR,
                                                f"input[name='{name}']")
                hint     = get_field_hint(driver, r)
                question = _get_label_for_field(driver, r)
                # Collect radio option labels
                radio_opts = []
                for radio in group:
                    try:
                        lbl = _get_label_for_field(driver, radio)
                        radio_opts.append((radio, lbl))
                    except Exception:
                        radio_opts.append((radio, ""))

                answer = smart_answer(hint)
                if answer is None:
                    answer = ai_answer(question or hint,
                                       field_type="radio",
                                       options=[lbl for _, lbl in radio_opts])
                answer_l = (answer or "yes").lower()

                best = None
                for radio, lbl in radio_opts:
                    if answer_l in lbl.lower() or lbl.lower() in answer_l:
                        best = radio
                        break
                target = best or (group[0] if group else None)
                if target:
                    driver.execute_script("arguments[0].click();", target)
                seen.add(name)
            except Exception:
                pass
    except Exception:
        pass

    # ── Checkboxes ────────────────────────────────────────────────────────
    # Handle two patterns:
    # 1. Single required consent checkbox  → check it ("I consent", GDPR etc.)
    # 2. Multi-checkbox group ("Select all that apply") → check "Not Applicable"
    #    or the first option if "Not Applicable" is absent
    try:
        # Find all visible checkbox groups
        all_cbs = [cb for cb in driver.find_elements(
            By.CSS_SELECTOR, "input[type='checkbox']")
            if cb.is_displayed()]

        # Group checkboxes by their fieldset/parent container
        # Simple approach: if only 1 checkbox visible → consent type, check it
        # If multiple visible → group, pick "Not Applicable" or first
        if len(all_cbs) == 1:
            cb = all_cbs[0]
            if not cb.is_selected():
                driver.execute_script("arguments[0].click();", cb)
        elif len(all_cbs) > 1:
            # Check if any are already selected
            any_selected = any(cb.is_selected() for cb in all_cbs)
            if not any_selected:
                # Try to find and click "Not Applicable" first
                clicked = False
                for cb in all_cbs:
                    try:
                        lbl = _get_label_for_field(driver, cb) or ""
                        if "not applicable" in lbl.lower():
                            driver.execute_script("arguments[0].click();", cb)
                            clicked = True
                            break
                    except Exception:
                        pass
                # Also check for second group "Not Applicable" (the LinkedIn/MS question has 2 groups)
                if not clicked:
                    driver.execute_script("arguments[0].click();", all_cbs[0])

            # Handle second checkbox group separately — look for required groups
            # by finding fieldsets or divs containing unchecked checkbox groups
            try:
                fieldsets = driver.find_elements(By.CSS_SELECTOR,
                    "fieldset, div[data-test-form-builder-checkbox-group]")
                for fs in fieldsets:
                    try:
                        group_cbs = [c for c in fs.find_elements(
                            By.CSS_SELECTOR, "input[type='checkbox']")
                            if c.is_displayed()]
                        if not group_cbs:
                            continue
                        if any(c.is_selected() for c in group_cbs):
                            continue   # already has a selection
                        # Pick "Not Applicable" or first option
                        clicked = False
                        for c in group_cbs:
                            lbl = _get_label_for_field(driver, c) or ""
                            if "not applicable" in lbl.lower():
                                driver.execute_script("arguments[0].click();", c)
                                clicked = True
                                break
                        if not clicked:
                            driver.execute_script("arguments[0].click();", group_cbs[0])
                    except Exception:
                        pass
            except Exception:
                pass
    except Exception:
        pass


def _modal_buttons(driver):
    """Return navigation buttons inside the Easy Apply modal.
    Tries multiple selectors and merges results.
    Excludes close/dismiss/X buttons that would discard the form."""
    seen_ids = set()
    buttons  = []

    # Try all selectors — merge unique buttons across all matches
    for sel in [
        "dialog button",
        "div[role='dialog'] button",
        ".jobs-easy-apply-modal button",
        ".artdeco-modal button",
        # Broader fallback — any visible modal-like container
        "[class*='modal'] button",
        "[class*='apply'] button",
    ]:
        try:
            for b in driver.find_elements(By.CSS_SELECTOR, sel):
                try:
                    bid = id(b)   # object identity
                    # Use location as dedup key (more reliable than object id)
                    loc = b.location
                    key = (loc['x'], loc['y'])
                    if key in seen_ids:
                        continue
                    seen_ids.add(key)
                    buttons.append(b)
                except Exception:
                    pass
        except Exception:
            pass

    # If nothing found via modal selectors, fall back to ALL visible buttons
    # (happens when LinkedIn uses non-standard modal markup)
    if not buttons:
        try:
            buttons = driver.find_elements(By.TAG_NAME, "button")
        except Exception:
            pass

    result = []
    for b in buttons:
        if not _btn_visible(b):
            continue
        try:
            aria = (b.get_attribute("aria-label") or "").lower()
            txt  = (b.text or "").strip().lower()
            inner = (driver.execute_script(
                "return arguments[0].innerText||''", b) or "").strip().lower()
            combined_text = txt + " " + inner

            # Exclude close / dismiss / X buttons
            if any(k in aria for k in ["dismiss", "close modal", "discard", "exit"]):
                continue
            # Exclude icon-only with no text at all
            if not combined_text.strip() and not aria:
                continue
        except Exception:
            pass
        result.append(b)
    return result


def _btn_visible(btn):
    try:
        return btn.is_displayed() and btn.is_enabled()
    except Exception:
        return False


def _btn_text(btn, driver=None):
    """Return normalised combined text+aria-label+innerText for a button."""
    try:
        txt   = (btn.text or "").strip().lower()
        aria  = (btn.get_attribute("aria-label") or "").strip().lower()
        inner = ""
        if driver:
            try:
                inner = (driver.execute_script(
                    "return arguments[0].innerText||''", btn) or "").strip().lower()
            except Exception:
                pass
        return txt + " " + aria + " " + inner
    except Exception:
        return ""


def click_next_button(driver):
    """Click the next/review/submit button in the modal.
    Returns 'submitted', 'next', or None."""

    SUBMIT_KEYWORDS = {"submit"}
    NEXT_KEYWORDS   = {"review", "next", "continue"}

    # ── 1. aria-label exact-match (fastest) ───────────────────────────────
    for label in ["Submit application", "submit application",
                  "Review your application"]:
        try:
            btn = driver.find_element(By.CSS_SELECTOR,
                                      f"button[aria-label='{label}']")
            if _btn_visible(btn):
                driver.execute_script("arguments[0].click();", btn)
                return "submitted" if "submit" in label.lower() else "next"
        except Exception:
            pass
    for label in ["Continue to next step", "Next"]:
        try:
            btn = driver.find_element(By.CSS_SELECTOR,
                                      f"button[aria-label='{label}']")
            if _btn_visible(btn):
                driver.execute_script("arguments[0].click();", btn)
                return "next"
        except Exception:
            pass

    # ── 2. Text-based search — re-fetch buttons fresh to avoid stale refs ─
    modal_btns = _modal_buttons(driver)

    # Pass 1 — Submit
    for btn in reversed(modal_btns):
        try:
            combined = _btn_text(btn, driver)
            if any(k in combined for k in SUBMIT_KEYWORDS):
                driver.execute_script("arguments[0].click();", btn)
                return "submitted"
        except Exception:
            pass

    # Pass 2 — Next / Review / Continue
    for btn in reversed(modal_btns):
        try:
            combined = _btn_text(btn, driver)
            if any(k in combined for k in NEXT_KEYWORDS):
                driver.execute_script("arguments[0].click();", btn)
                return "next"
        except Exception:
            pass

    # ── 3. Debug ───────────────────────────────────────────────────────────
    if modal_btns:
        print("\n      [DEBUG] Modal buttons found but none matched:")
        for btn in modal_btns:
            try:
                txt  = repr((btn.text or "").strip())
                aria = repr(btn.get_attribute("aria-label") or "")
                js_t = repr(driver.execute_script(
                    "return arguments[0].innerText||'';", btn).strip())
                print(f"        text={txt}  aria={aria}  innerText={js_t}")
            except Exception:
                pass   # skip stale elements silently
    else:
        print("\n      [DEBUG] No buttons found in modal at all — modal may not be open.")

    return None


def _modal_is_open(driver):
    """Return True if the Easy Apply modal is currently visible."""
    for sel in [
        "dialog",
        "div[role='dialog']",
        ".jobs-easy-apply-modal",
        ".artdeco-modal",
    ]:
        try:
            els = driver.find_elements(By.CSS_SELECTOR, sel)
            if any(e.is_displayed() for e in els):
                return True
        except Exception:
            pass
    return False


def _confirm_submission(driver, timeout=3):
    """Return True only when LinkedIn shows an explicit post-submit success signal."""
    # LinkedIn shows a toast / success banner after submission —
    # look for known text anchors or the 'Done' dismiss button.
    success_selectors = [
        # 'Your application was sent' banner text (various LinkedIn versions)
        "//*[contains(text(),'application was sent')]",
        "//*[contains(text(),'Applied')]",
        "//*[contains(text(),'successfully submitted')]",
        # Post-submit 'Done' button that closes the success screen
        "button[aria-label='Done']",
        "button[aria-label='Dismiss']",
    ]
    deadline = time.time() + timeout
    while time.time() < deadline:
        for sel in success_selectors:
            try:
                if sel.startswith("/"):
                    el = driver.find_element(By.XPATH, sel)
                else:
                    el = driver.find_element(By.CSS_SELECTOR, sel)
                if el.is_displayed():
                    return True
            except Exception:
                pass
        time.sleep(0.5)
    return False


def fill_easy_apply(driver, resume_path=None):
    """Walk through Easy Apply multi-step form and submit."""
    submitted = False
    _resume = resume_path or RESUME_PATH

    for step in range(50):
        pause(0.4, 0.6)
        check_easy_apply_limit(driver)   # stop immediately if daily limit hit
        handle_save_application_dialog(driver)
        if step == 0:
            dismiss_popups(driver)
        print(f"      Step {step + 1}...", end=" ", flush=True)

        check_easy_apply_limit(driver)   # check again after render
        fill_form_fields(driver, resume_path=_resume)
        pause(0.3, 0.5)
        handle_save_application_dialog(driver)

        result = click_next_button(driver)
        print(result or "no button found")

        if result == "submitted":
            pause(1, 1.5)                       # reduced from 1.5-2s
            # Verify via explicit success indicator
            if _confirm_submission(driver):
                submitted = True
            else:
                # If modal closed but no success banner — treat as uncertain
                if not _modal_is_open(driver):
                    print("    [?] Modal closed after Submit click but no "
                          "success banner found — marking as submitted.")
                    submitted = True
                else:
                    print("    [!] Submit clicked but modal still open and no "
                          "success banner — treating as failed.")
            # Dismiss any lingering success screen
            for sel in ["button[aria-label='Done']",
                        "button[aria-label='Dismiss']"]:
                try:
                    driver.find_element(By.CSS_SELECTOR, sel).click()
                    break
                except Exception:
                    pass
            if submitted:
                print("    [+] Application submitted successfully!")
            return submitted

        if result is None:
            # No navigation button found
            if not _modal_is_open(driver):
                # Modal closed WITHOUT us clicking Submit — NOT a submission
                print("    [!] Modal closed without a Submit click — "
                      "treating as skipped.")
                return False
            print("    [!] Stuck on step — stopping.")
            break

    return False

def close_modal(driver):
    """Dismiss / discard the Easy Apply modal safely."""
    # First try the native <dialog> close button (LinkedIn new UI)
    try:
        dialog = driver.find_element(By.CSS_SELECTOR, "dialog")
        if dialog.is_displayed():
            # Look for a Dismiss/Close/Discard button inside the dialog
            for btn in dialog.find_elements(By.TAG_NAME, "button"):
                try:
                    aria = (btn.get_attribute("aria-label") or "").lower()
                    txt  = (btn.text or "").lower()
                    if any(k in aria + txt for k in ["dismiss", "discard", "close"]):
                        driver.execute_script("arguments[0].click();", btn)
                        pause(0.5, 1)
                        # Confirm discard if prompted
                        for sel2 in [
                            "button[data-control-name='discard_application_confirm_btn']",
                            "button[aria-label='Discard']",
                        ]:
                            try:
                                driver.find_element(By.CSS_SELECTOR, sel2).click()
                                pause(0.5, 1)
                            except Exception:
                                pass
                        return
                except Exception:
                    pass
    except Exception:
        pass

    # Fallback for older LinkedIn UI
    for sel in [
        "button[aria-label='Dismiss']",
        "button[data-control-name='discard_application_confirm_btn']",
        "button[aria-label='Discard']",
    ]:
        try:
            driver.find_element(By.CSS_SELECTOR, sel).click()
            pause(0.5, 1)
        except Exception:
            pass

def process_jobs(driver):
    job_ids = collect_job_ids(driver)
    print(f"\n[*] Total jobs to process: {len(job_ids)}\n")

    if not job_ids:
        print("[!] No jobs found.")
        return

    applied, skipped = [], []

    for idx, job_id in enumerate(job_ids):
        job_url = f"https://www.linkedin.com/jobs/view/{job_id}/"
        print(f"\n[{idx+1}/{len(job_ids)}] {job_url}")

        try:
            # Navigate to job page — retry once if LinkedIn redirects away
            for _nav_try in range(2):
                try:
                    driver.get(job_url)
                except Exception:
                    driver.execute_script("window.stop();")
                wait_for_page(driver, timeout=12)
                current_url = driver.current_url
                if "jobs/view" in current_url:
                    break  # on correct page
                # Redirected — wait 1s and try once more
                print(f"    [!] Redirected to {current_url[:60]}... retrying")
                time.sleep(1)

            dismiss_popups(driver)

            print(f"    URL    : {driver.current_url[:80]}")
            title, company = get_job_info(driver)
            print(f"    Title  : {title}")
            print(f"    Company: {company}")

            # Read JD and generate tailored resume via Groq
            jd_text = extract_jd(driver)
            if jd_text:
                print(f"    JD     : {len(jd_text)} chars — tailoring resume...")
                current_resume = generate_tailored_resume(jd_text, job_id)
            else:
                print(f"    JD     : not found — using default resume")
                current_resume = RESUME_PATH

            # Poll every 0.4s for up to 8s for the Apply/Continue button
            apply_btn = None
            deadline  = time.time() + 8
            while time.time() < deadline:
                is_last = time.time() + 0.5 >= deadline
                apply_btn, _ = find_apply_btn(driver, debug=is_last)
                if apply_btn is not None:
                    break
                time.sleep(0.4)

            if apply_btn is not None:
                print("    -> Clicking Easy Apply...")
                driver.execute_script("arguments[0].scrollIntoView(true);", apply_btn)
                pause(0.3, 0.5)
                driver.execute_script("arguments[0].click();", apply_btn)
                pause(0.6, 1)
                check_easy_apply_limit(driver)   # stop if daily limit hit
                dismiss_popups(driver)
                success = fill_easy_apply(driver, resume_path=current_resume)
                if success:
                    applied.append((title, company, job_url))
                else:
                    close_modal(driver)
                    skipped.append((title, company, job_url))
            else:
                if is_already_applied(driver):
                    print("    -> Already applied to this job — skipping.")
                else:
                    print("    -> Easy Apply button not found — skipping.")
                skipped.append((title, company, job_url))

        except EasyApplyLimitReached:
            print("\n[!] LinkedIn daily Easy Apply limit reached — stopping for today.")
            print(f"    Applied so far: {len(applied)} jobs. Try again tomorrow.")
            break
        except Exception as e:
            print(f"    [!] Error: {e}")
            skipped.append(("Error", "", job_url))

        pause(MIN_DELAY, MAX_DELAY)

    # ── Summary ─────────────────────────────
    print("\n" + "="*60)
    print("JOB APPLICATION SUMMARY")
    print("="*60)
    print(f"Easy Apply submitted : {len(applied)}")
    print(f"Skipped/Errors       : {len(skipped)}")
    if applied:
        print("\nApplied:")
        for t, c, u in applied:
            print(f"  - {t} @ {c}")
    print(f"\n[Phase 2 — External jobs with dynamic resume: Coming soon]")

def debug_single_job(job_url):
    """Directly process one job URL — skips search, goes straight to apply."""
    driver = init_driver()
    try:
        login(driver)
        print(f"\n[DEBUG] Going directly to: {job_url}")
        try:
            driver.get(job_url)
        except Exception:
            # TimeoutException is fine — page partially loaded, stop it and continue
            try:
                driver.execute_script("window.stop();")
            except Exception:
                pass
        time.sleep(4)
        dismiss_popups(driver)
        time.sleep(1)

        # ── Full flow: title → JD → tailored resume → apply ──────────────
        print(f"\n[DEBUG] URL    : {driver.current_url}")

        # Title & company from page title
        title, company = get_job_info(driver)
        print(f"[DEBUG] Title  : {title}")
        print(f"[DEBUG] Company: {company}")

        # Extract JD
        print(f"[DEBUG] Extracting JD...")
        jd = extract_jd(driver)
        if jd:
            print(f"[DEBUG] JD found ({len(jd)} chars):\n--- JD START ---\n{jd[:800]}\n--- JD END ---")
        else:
            print("[DEBUG] JD NOT FOUND — will use default resume")

        # Generate tailored resume
        job_id_m = re.search(r'/jobs/view/(\d+)/', job_url)
        job_id   = job_id_m.group(1) if job_id_m else "debug"
        if jd:
            print(f"\n[DEBUG] Generating tailored resume via Groq...")
            resume_to_use = generate_tailored_resume(jd, job_id)
        else:
            resume_to_use = RESUME_PATH
        print(f"[DEBUG] Resume : {resume_to_use}")

        # Now click Apply
        print("\n[DEBUG] Looking for Apply/Continue button...")
        apply_btn, _ = find_apply_btn(driver, debug=True)
        if apply_btn is not None:
            print("    -> Clicking Easy Apply...")
            driver.execute_script("arguments[0].scrollIntoView(true);", apply_btn)
            pause(0.5, 1)
            driver.execute_script("arguments[0].click();", apply_btn)
            pause(1, 1.5)
            check_easy_apply_limit(driver)
            dismiss_popups(driver)
            success = fill_easy_apply(driver, resume_path=resume_to_use)
            if success:
                print("    [+] Applied successfully!")
            else:
                print("    [!] Application not completed.")
                close_modal(driver)
        else:
            print("    [!] Apply button not found.")

        input("\nPress ENTER to close...")
    except KeyboardInterrupt:
        pass
    finally:
        try:
            driver.quit()
        except Exception:
            pass


def main():
    driver = init_driver()
    try:
        login(driver)
        process_jobs(driver)
        print("\n[*] All done!")
        input("Press ENTER to close the browser...")
    except KeyboardInterrupt:
        print("\n[!] Interrupted by user.")
    finally:
        try:
            driver.quit()
        except Exception:
            pass

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--debug-job":
        # Usage: python linkedin_job_apply.py --debug-job <url>
        url = sys.argv[2] if len(sys.argv) > 2 else "https://www.linkedin.com/jobs/view/4489561638/"
        debug_single_job(url)
    else:
        main()

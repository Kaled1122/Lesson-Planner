# ------------------------------------------------------------
# app.py — Flask backend for automatic English Lesson Plan generation
# ------------------------------------------------------------

import os
from flask import Flask, request, jsonify
from flask_cors import CORS
from openai import OpenAI
import tempfile
from PyPDF2 import PdfReader
from docx import Document
from openpyxl import load_workbook
from PIL import Image
import pytesseract

# ------------------------------------------------------------
# ✅ SETUP
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app)

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are an expert English Language Teaching (ELT) planner, specializing in ALC- and communicative-style lesson design.
Your job is to analyze uploaded materials (PDFs, Word files, Excel sheets, or extracted OCR text)
and create a complete, structured English lesson plan automatically.

Follow this exact structure:

🏫 ENGLISH LESSON PLAN

### Lesson Information
- Lesson Title:
- Book / Unit:
- Level:
- Lesson Type:
- Duration:
- Date:

### Learning Objectives
(2–3 measurable objectives)

### Target Language
| Component | Content |
|------------|----------|
| Grammar / Structure | |
| Vocabulary | |
| Pronunciation Focus | |
| Functional Language | |

### Materials / Resources
(List materials available or inferred from content)

### Lesson Stages
| Stage | Timing | Purpose / Description | Teacher’s Role | Students’ Role |
|--------|---------|----------------------|----------------|----------------|
| Warm-up / Lead-in | | | | |
| Presentation | | | | |
| Practice (Controlled) | | | | |
| Production (Freer) | | | | |
| Assessment / Wrap-up | | | | |
| Extension / Homework | | | | |

### Assessment & Feedback
(Describe method of assessment and feedback)

### Reflection / Notes
(Teacher notes, adjustments, next steps)

Guidelines:
- Keep tone professional and concise.
- Use B2-level teacher-facing language.
- Always fill all segments logically even when inferring context.
"""

# ------------------------------------------------------------
# 🧩 UTILITIES
# ------------------------------------------------------------

def extract_text_from_file(file):
    """Extract text from PDF, DOCX, XLSX, or image files."""
    name = file.filename.lower()
    text = ""

    if name.endswith(".pdf"):
        reader = PdfReader(file)
        text = "\n".join([page.extract_text() or "" for page in reader.pages])

    elif name.endswith(".docx"):
        doc = Document(file)
        text = "\n".join([para.text for para in doc.paragraphs])

    elif name.endswith(".xlsx"):
        wb = load_workbook(file)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                text += " ".join([str(cell) for cell in row if cell]) + "\n"

    elif name.endswith((".jpg", ".jpeg", ".png")):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.save(tmp.name)
            img = Image.open(tmp.name)
            text = pytesseract.image_to_string(img)

    else:
        text = file.read().decode("utf-8", errors="ignore")

    return text.strip()


# ------------------------------------------------------------
# ⚙️ ROUTES
# ------------------------------------------------------------

@app.route("/generate", methods=["POST"])
def generate_lesson_plan():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded"}), 400

    file = request.files["file"]
    text_content = extract_text_from_file(file)

    if not text_content:
        return jsonify({"error": "Could not extract text"}), 400

    prompt = f"Extracted content:\n{text_content}\n\nCreate a full English lesson plan based on this material."

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.4
    )

    lesson_plan = response.choices[0].message.content
    return jsonify({"lesson_plan": lesson_plan})


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Lesson Plan Generator API is running"})


# ------------------------------------------------------------
# 🚀 RUN LOCALLY
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

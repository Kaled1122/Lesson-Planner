import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from openai import OpenAI
from PyPDF2 import PdfReader
from docx import Document
from openpyxl import load_workbook
from PIL import Image
import pytesseract
import tempfile
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------------------------------------------
# ✅ SYSTEM PROMPT (with Interaction Pattern)
# ------------------------------------------------------------
SYSTEM_PROMPT = """
You are an expert English Language Teaching (ELT) planner and mentor.
Your role is to help teachers prepare their lessons to the highest professional standard
based on official teaching performance rubrics.

Your job is to analyze the teacher’s uploaded materials and provided inputs,
then generate:
1. A complete, structured English lesson plan tailored to the lesson content.
2. A professional coaching guide that helps the teacher strengthen their plan and delivery
   to achieve the selected level of readiness (Good or Outstanding).

INPUT DETAILS
You will receive:
- Teacher Name
- Lesson Number
- Lesson Duration
- Learner Profile
- Anticipated Problems
- Target Rating: Good or Outstanding
- Extracted lesson content (from uploaded files)

PURPOSE
This system is for teacher preparation only.
Do not evaluate, grade, or score the teacher.
Instead, act as a professional mentor who helps the teacher refine the lesson plan
to maximize readiness for a formal observation based on the official rubric.

Your output must emphasize:
- What to refine before the observation.
- What behaviors, phrasing, or techniques to demonstrate during the lesson.
- What materials or evidence to prepare (visuals, timing cues, resources).
- How to meet or exceed rubric expectations for the chosen target level.

INTERPRETING THE INPUT
When analyzing the uploaded material:
- Identify its main focus (grammar, vocabulary, listening, reading, speaking, or writing).
- Infer learner level (e.g., CEFR A2/B1/B2) based on complexity of content.
- Extract key language items, functions, and themes.
- Use these as the foundation for the Presentation, Practice, and Production stages.
- Align your lesson structure with ALC/DLI-style methodology when possible.
- When designing lesson stages, include an “Interaction Pattern” column
  showing how communication occurs at each stage (for example: T→S, S↔S, Group Work, Pair Work, Whole Class).

STYLE AND TONE
Maintain a developmental and coaching tone — supportive, encouraging, and professional.
Avoid symbols, markdown, or emojis. Use plain text only.

OUTPUT STRUCTURE
Your response must contain two main sections plus metadata.

SECTION 1 — Complete Lesson Plan
(Include headers: Lesson Information, Learning Objectives, Target Language, Lesson Stages, Differentiation, Assessment and Feedback, Reflection and Notes.)

Lesson Stages Table Format:
Stage | Timing | Purpose / Description | Teacher’s Role | Learners’ Role | Interaction Pattern
Warm-up / Lead-in
Presentation
Practice (Controlled)
Production (Freer)
Assessment / Wrap-up
Extension / Homework

SECTION 2 — Observation Readiness Coaching Guide
Provide guidance under eight domains: Lesson Plan Quality, Aims and Objectives, Classroom Management,
Teaching Aids and Resources, Communication Skills, Interaction and Questioning, Learning Check and Summary,
and Professional Presence.

Metadata
Include generation date, version, and target readiness level.

Style Rules
Use plain text only, no markdown, no symbols, no emojis.
Output must be clean and suitable for DOCX export.
"""

# ------------------------------------------------------------
# ✅ TEXT EXTRACTION FUNCTION
# ------------------------------------------------------------
def extract_text_from_file(file):
    name = file.filename.lower()
    text = ""
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        text = "\n".join([page.extract_text() or "" for page in reader.pages])
    elif name.endswith(".docx"):
        doc = Document(file)
        text = "\n".join([p.text for p in doc.paragraphs])
    elif name.endswith(".xlsx"):
        wb = load_workbook(file)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                text += " ".join([str(c) for c in row if c]) + "\n"
    elif name.endswith((".png", ".jpg", ".jpeg")):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.save(tmp.name)
            img = Image.open(tmp.name)
            text = pytesseract.image_to_string(img)
    else:
        text = file.read().decode("utf-8", errors="ignore")
    return text.strip()

# ------------------------------------------------------------
# ✅ MAIN ROUTE: Generate Lesson Plan
# ------------------------------------------------------------
@app.route("/generate", methods=["POST"])
def generate_lesson_plan():
    try:
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        text_content = extract_text_from_file(file)
        if not text_content:
            return jsonify({"error": "Could not extract text"}), 400

        teacher_name = request.form.get("teacher_name", "N/A")
        lesson_number = request.form.get("lesson_number", "N/A")
        lesson_duration = request.form.get("lesson_duration", "N/A")
        learner_profile = request.form.get("learner_profile", "N/A")
        anticipated_problems = request.form.get("anticipated_problems", "N/A")
        target_rating = request.form.get("target_rating", "Good")

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        user_prompt = f"""
Teacher Name: {teacher_name}
Lesson Number: {lesson_number}
Lesson Duration: {lesson_duration}
Learner Profile: {learner_profile}
Anticipated Problems: {anticipated_problems}
Target Rating: {target_rating}
Timestamp: {timestamp}

Extracted Lesson Content:
{text_content}
"""

        # ---- AI Call ----
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
        )
        lesson_plan_text = response.choices[0].message.content.strip()

        # ---- Create DOCX ----
        doc = Document()
        doc.add_heading("AI Lesson Plan — Observation Readiness Coach", level=0)
        doc.add_paragraph(f"Generated on {timestamp}")
        doc.add_paragraph(f"Target Level: {target_rating}")
        doc.add_paragraph("")

        lines = lesson_plan_text.split("\n")
        for i, line in enumerate(lines):
            if "Target Language" in line:
                doc.add_heading("Target Language", level=1)
                table = doc.add_table(rows=5, cols=2)
                hdrs = ["Component", "Content"]
                for idx, hdr in enumerate(hdrs):
                    table.rows[0].cells[idx].text = hdr
                components = ["Grammar / Structure", "Vocabulary", "Pronunciation Focus", "Functional Language"]
                for j, comp in enumerate(components, start=1):
                    table.rows[j].cells[0].text = comp
                doc.add_paragraph("")

            elif "Lesson Stages" in line:
                doc.add_heading("Lesson Stages", level=1)
                table = doc.add_table(rows=7, cols=6)
                headers = ["Stage", "Timing", "Purpose / Description", "Teacher’s Role", "Learners’ Role", "Interaction Pattern"]
                for idx, hdr in enumerate(headers):
                    table.rows[0].cells[idx].text = hdr
                stages = ["Warm-up / Lead-in", "Presentation", "Practice (Controlled)", "Production (Freer)", "Assessment / Wrap-up", "Extension / Homework"]
                for j, stage in enumerate(stages, start=1):
                    table.rows[j].cells[0].text = stage
                doc.add_paragraph("")

            elif line.strip():
                doc.add_paragraph(line.strip())

        filename = f"Lesson_Plan_{teacher_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx"
        file_path = os.path.join(tempfile.gettempdir(), filename)
        doc.save(file_path)

        return send_file(file_path, as_attachment=True, download_name=filename)

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500

# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "AI Lesson Planner (Observation Readiness Coach) is running"})

# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from openai import OpenAI
from PyPDF2 import PdfReader
from docx import Document
from docx.shared import Inches, Cm
from docx.enum.section import WD_ORIENT
from openpyxl import load_workbook
from PIL import Image
import pytesseract
import tempfile
from datetime import datetime
import re

# ------------------------------------------------------------
# APP SETUP
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------------------------------------------
# SYSTEM PROMPT
# ------------------------------------------------------------
SYSTEM_PROMPT = """
You are an expert English Language Teaching (ELT) mentor.
Generate a complete English lesson plan and coaching guide in plain text.
Each section must begin with clear headers exactly as listed below.

Required structure:
1. Lesson Information
2. Learning Objectives
3. Target Language
4. Lesson Stages
5. Differentiation
6. Assessment and Feedback
7. Reflection and Notes
8. Observation Readiness Coaching Guide

For Lesson Stages, use six subcolumns:
Stage | Timing | Purpose / Description | Teacher’s Role | Learners’ Role | Interaction Pattern

Avoid markdown, symbols, or emojis.
Keep everything clear and printable.
"""

# ------------------------------------------------------------
# TEXT EXTRACTION FUNCTION
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
# MAIN ROUTE
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

        # ---- AI CALL ----
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.4,
        )
        plan_text = response.choices[0].message.content.strip()

        # ------------------------------------------------------------
        # CREATE LANDSCAPE DOCX
        # ------------------------------------------------------------
        doc = Document()
        section = doc.sections[0]
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = section.page_height, section.page_width
        section.top_margin = section.bottom_margin = Inches(0.7)
        section.left_margin = section.right_margin = Inches(0.7)

        doc.add_heading("AI Lesson Plan — Observation Readiness Coach", level=0)
        doc.add_paragraph(f"Generated on: {timestamp}")
        doc.add_paragraph(f"Target Level: {target_rating}")
        doc.add_paragraph("")

        # ------------------------------------------------------------
        # PARSE AI OUTPUT BY HEADERS
        # ------------------------------------------------------------
        sections = re.split(r"\n(?=\d\.)", plan_text)
        content = { "Lesson Information": "", "Learning Objectives": "",
                    "Target Language": "", "Lesson Stages": "",
                    "Differentiation": "", "Assessment and Feedback": "",
                    "Reflection and Notes": "", "Observation Readiness Coaching Guide": "" }

        for block in sections:
            for key in content.keys():
                if key.lower() in block.lower():
                    content[key] = block.strip()
                    break

        # ------------------------------------------------------------
        # LESSON INFO
        # ------------------------------------------------------------
        doc.add_heading("Lesson Information", level=1)
        doc.add_paragraph(content["Lesson Information"] or "(AI section)")
        doc.add_paragraph("")

        # ------------------------------------------------------------
        # OBJECTIVES
        # ------------------------------------------------------------
        doc.add_heading("Learning Objectives", level=1)
        doc.add_paragraph(content["Learning Objectives"] or "(AI section)")
        doc.add_paragraph("")

        # ------------------------------------------------------------
        # TARGET LANGUAGE TABLE
        # ------------------------------------------------------------
        doc.add_heading("Target Language", level=1)
        table1 = doc.add_table(rows=5, cols=2)
        table1.style = "Table Grid"
        headers = ["Component", "Content"]
        for i, hdr in enumerate(headers):
            table1.rows[0].cells[i].text = hdr
        components = ["Grammar / Structure", "Vocabulary", "Pronunciation Focus", "Functional Language"]
        for j, comp in enumerate(components, start=1):
            table1.rows[j].cells[0].text = comp
            table1.rows[j].cells[1].text = "(AI generated content)"
        doc.add_paragraph("")

        # ------------------------------------------------------------
        # LESSON STAGES TABLE
        # ------------------------------------------------------------
        doc.add_heading("Lesson Stages", level=1)
        table2 = doc.add_table(rows=7, cols=6)
        table2.style = "Table Grid"
        headers = ["Stage", "Timing", "Purpose / Description", "Teacher’s Role", "Learners’ Role", "Interaction Pattern"]
        for i, hdr in enumerate(headers):
            table2.rows[0].cells[i].text = hdr
        stages = [
            "Warm-up / Lead-in",
            "Presentation",
            "Practice (Controlled)",
            "Production (Freer)",
            "Assessment / Wrap-up",
            "Extension / Homework",
        ]
        for j, stage in enumerate(stages, start=1):
            table2.rows[j].cells[0].text = stage
            table2.rows[j].cells[1].text = ""
            table2.rows[j].cells[2].text = "(AI description)"
            table2.rows[j].cells[3].text = "(AI teacher role)"
            table2.rows[j].cells[4].text = "(AI learner role)"
            table2.rows[j].cells[5].text = "(AI pattern)"
        doc.add_paragraph("")

        # ------------------------------------------------------------
        # DIFFERENTIATION / FEEDBACK / REFLECTION
        # ------------------------------------------------------------
        for section_name in ["Differentiation", "Assessment and Feedback", "Reflection and Notes"]:
            doc.add_heading(section_name, level=1)
            doc.add_paragraph(content[section_name] or "(AI section)")
            doc.add_paragraph("")

        # ------------------------------------------------------------
        # COACHING GUIDE
        # ------------------------------------------------------------
        doc.add_heading("Observation Readiness Coaching Guide", level=1)
        doc.add_paragraph(content["Observation Readiness Coaching Guide"] or "(AI section)")
        doc.add_paragraph("")

        # ------------------------------------------------------------
        # METADATA
        # ------------------------------------------------------------
        doc.add_heading("Metadata", level=1)
        doc.add_paragraph("Generated by: AI Lesson Planner v1.0")
        doc.add_paragraph(f"Target Readiness Level: {target_rating}")
        doc.add_paragraph(f"Teacher: {teacher_name}")
        doc.add_paragraph(f"Lesson Number: {lesson_number}")
        doc.add_paragraph(f"Date: {timestamp}")

        # SAVE AND RETURN FILE
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
    return jsonify({"message": "AI Lesson Planner (Landscape Mode) is running"})
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

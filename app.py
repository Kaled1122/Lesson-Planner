import os
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from openai import OpenAI
from PyPDF2 import PdfReader
from docx import Document
from docx.shared import Inches
from docx.enum.section import WD_ORIENT
from openpyxl import load_workbook
from PIL import Image
import pytesseract
import tempfile
from datetime import datetime

# --------------------------------------------------------------------
# APP SETUP
# --------------------------------------------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# --------------------------------------------------------------------
# RUBRIC-AWARE SYSTEM PROMPT
# --------------------------------------------------------------------
SYSTEM_PROMPT = """
You are an expert English Language Teaching (ELT) mentor and lesson designer.
Your role is to help teachers produce complete, professional lesson plans that
prepare them for classroom observation according to the official rubric below.

Do not evaluate the teacher.
Instead, generate a full, AI-filled lesson plan and a professional coaching guide
that aligns with the selected performance level: “Good” or “Outstanding.”

=====================================================================
RUBRIC REFERENCE: Teaching Observation Standards
=====================================================================
When producing your response, ensure that ALL of the following areas
are represented with the quality level that matches the selected Target Rating.

1. Lesson Plan  
   - GOOD: Clear, structured plan identifying resources and timing.  
   - OUTSTANDING: Highly detailed with timed stages, varied activities, 
     and resources that clearly meet learner needs.

2. Aims & Objectives  
   - GOOD: Objectives shared with learners at the start or during lesson; 
     clear learning purpose.  
   - OUTSTANDING: Comprehensive introduction; learners can explain the
     lesson purpose themselves.

3. Student & Classroom Management  
   - GOOD: Enforces clear routines; maintains order; positive relationship.  
   - OUTSTANDING: Inspires motivation; handles behaviour proactively; 
     fully compliant with procedures and professional tone.

4. Teaching Aids & Resources  
   - GOOD: Well-prepared resources supporting understanding.  
   - OUTSTANDING: Variety of aids fully integrated into delivery and
     continuous improvement.

5. Communication Skills  
   - GOOD: Clear voice, effective verbal/non-verbal communication, maintains interest.  
   - OUTSTANDING: Engaging, confident delivery using strong expression,
     sustained motivation, and excellent rapport.

6. Variety & Effectiveness of Interaction  
   - GOOD: Pair and group work planned; mostly effective interactions.  
   - OUTSTANDING: Dynamic, learner-centred activity; teacher facilitates,
     learners lead discussion and tasks.

7. Question & Answer Techniques  
   - GOOD: Mix of open and closed questions; checks understanding.  
   - OUTSTANDING: Range of higher-order questioning; probing, reflective,
     encouraging reasoning and autonomy.

8. Check of Learning & Summary  
   - GOOD: Reviews key points and confirms understanding at end.  
   - OUTSTANDING: Continuous checks; analytical summary linked to aims;
     learners self-assess progress.

9. Practical Activity (Safety, Explanation, Inclusion)  
   - GOOD: Clear safety brief, logical task explanation, learners engaged.  
   - OUTSTANDING: Comprehensive safety intro, strong learner ownership,
     inclusive engagement for all cadets.

=====================================================================
APPLICATION LOGIC
=====================================================================
When the teacher selects "Good":
- Write with a structured, procedural tone.
- Focus on clarity, pacing, and consistent learner engagement.

When the teacher selects "Outstanding":
- Write with an inspiring, developmental tone.
- Include evidence of differentiation, motivation, creativity, and learner autonomy.

=====================================================================
OUTPUT STRUCTURE
=====================================================================
SECTION 1 — Complete Lesson Plan  
Include:  
Lesson Information, Learning Objectives, Target Language, Lesson Stages, 
Differentiation, Assessment and Feedback, Reflection and Notes.

Lesson Stages Table must include:  
Stage | Timing | Purpose / Description | Teacher’s Role | Learners’ Role | Interaction Pattern

SECTION 2 — Observation Readiness Coaching Guide  
Provide practical mentoring advice under these domains:
Lesson Plan Quality, Aims & Objectives, Classroom Management,
Teaching Aids & Resources, Communication Skills, Interaction & Questioning,
Learning Check & Summary, Professional Presence.

=====================================================================
RUBRIC SELF-CHECK BEFORE OUTPUT
=====================================================================
Before finalizing your output:
1. Review your generated content against all rubric categories above.
2. Ensure that each area includes language and detail appropriate to the
   selected Target Rating.
3. Revise wording where necessary to make the plan fully compliant with
   rubric expectations.
4. Then produce the final, plain-text lesson plan and coaching guide.
=====================================================================
STYLE RULES
- Plain text only (no markdown, no symbols, no emojis).
- Use professional, supportive language.
- Make the output printable, editable, and observation-ready.
"""

# --------------------------------------------------------------------
# TEXT EXTRACTION FUNCTION
# --------------------------------------------------------------------
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

# --------------------------------------------------------------------
# MAIN ROUTE
# --------------------------------------------------------------------
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

        lesson_plan_text = response.choices[0].message.content.strip()

        # --------------------------------------------------------------------
        # CREATE LANDSCAPE DOCX WITH AI OUTPUT ONLY
        # --------------------------------------------------------------------
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

        # Write AI text directly, line by line
        for line in lesson_plan_text.split("\n"):
            line = line.strip()
            if not line:
                continue
            # Create simple table if AI used "|" separators
            if "|" in line:
                columns = [c.strip() for c in line.split("|")]
                if not hasattr(doc, "_current_table"):
                    doc._current_table = doc.add_table(rows=1, cols=len(columns))
                    doc._current_table.style = "Table Grid"
                    row = doc._current_table.rows[0]
                    for i, cell_text in enumerate(columns):
                        row.cells[i].text = cell_text
                else:
                    row = doc._current_table.add_row()
                    for i, cell_text in enumerate(columns):
                        row.cells[i].text = cell_text
            else:
                if hasattr(doc, "_current_table"):
                    delattr(doc, "_current_table")
                doc.add_paragraph(line)

        # --------------------------------------------------------------------
        # SAVE FILE
        # --------------------------------------------------------------------
        filename = f"Lesson_Plan_{teacher_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx"
        file_path = os.path.join(tempfile.gettempdir(), filename)
        doc.save(file_path)
        return send_file(file_path, as_attachment=True, download_name=filename)

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500

# --------------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "AI Lesson Planner (Rubric-Aware, Landscape) is running"})
# --------------------------------------------------------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

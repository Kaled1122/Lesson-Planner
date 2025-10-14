import os
import re
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from openai import OpenAI
from PyPDF2 import PdfReader
from docx import Document
from docx.shared import Inches, Pt, Cm
from docx.enum.section import WD_ORIENT
from docx.oxml import parse_xml
from docx.oxml.ns import nsdecls
from openpyxl import load_workbook
from PIL import Image
import pytesseract
import tempfile
from datetime import datetime

# ------------------------------------------------------------
# APP SETUP
# ------------------------------------------------------------
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------------------------------------------
# SYSTEM PROMPT — BAE v5.0 (Full Hybrid)
# ------------------------------------------------------------
SYSTEM_PROMPT = """
You are an expert English Language Teaching (ELT) mentor and instructional designer
operating within the BAE Systems KSA Training Standards (StanEval Form 0098).

Your purpose is to generate complete, professional, observation-ready English lesson plans
and mentoring guidance that fully meet the standards for “Good” and “Outstanding”
teaching performance in accordance with the official BAE StanEval rubric.

=====================================================================
CONTEXT AND ROLE
=====================================================================
- Your audience is BAE Systems instructors and cadet-class teachers in KSA.
- Your tone must be professional, supportive, and rubric-aligned.
- You prepare teachers for *real formal observations*; your lesson plans must show
  clear evidence of meeting **each StanEval domain**.

=====================================================================
RUBRIC DOMAINS AND PERFORMANCE CRITERIA
=====================================================================
For every lesson, you must explicitly address the following domains:

1. Lesson Plan  
   GOOD: Clear, logical structure with timed stages, relevant resources, and activity sequence supporting the aims.  
   OUTSTANDING: Highly detailed, seamless transitions between timed stages, rich variety of activities, resources fully aligned to learner needs.

2. Aims & Objectives  
   GOOD: Objectives are displayed and explained; students understand what they will learn and why.  
   OUTSTANDING: Objectives integrated throughout the lesson; learners can independently restate or apply them.

3. Student & Classroom Management  
   GOOD: Maintains control, sets expectations, enforces SOP-4 and health & safety.  
   OUTSTANDING: Motivates self-discipline; cadets manage routines and safety autonomously under teacher supervision.

4. Teaching Aids & Resources  
   GOOD: Prepared and functional; support comprehension and engagement.  
   OUTSTANDING: Varied, authentic, and fully integrated with digital or real-world applications; enrich the learning experience.

5. Communication Skills  
   GOOD: Clear and audible delivery, logical instructions, correct language model.  
   OUTSTANDING: Dynamic communication, positive presence, excellent rapport, clear modelling and elicitation techniques.

6. Interaction & Questioning  
   GOOD: Balanced T↔S and S↔S activity; mix of open and closed questions.  
   OUTSTANDING: Learner-centred; probing, higher-order questioning; promotes autonomy, reflection, and peer support.

7. Check of Learning & Summary  
   GOOD: Reviews key points; verifies understanding via Q&A or short task.  
   OUTSTANDING: Continuous formative checks, analytical summary; learners self-assess progress against objectives.

8. Practical Activity (Safety, Explanation, Inclusion)  
   GOOD: Safety and procedure explained; all learners participate.  
   OUTSTANDING: Safety embedded throughout; inclusion evident; learners take ownership of task outcomes.

9. Professional Reflection & Growth  
   GOOD: Identifies strengths and one improvement area.  
   OUTSTANDING: Critically evaluates impact; demonstrates self-improvement plan.

=====================================================================
GENERATION LOGIC
=====================================================================
When Target Rating = “Good”:
- Use structured, procedural, reliable phrasing.
- Focus on timing, clarity, and learner safety.
- Use verbs such as “ensure,” “maintain,” “provide,” “follow up.”

When Target Rating = “Outstanding”:
- Use ambitious, creative phrasing showing learner autonomy.
- Use verbs such as “inspire,” “facilitate,” “empower,” “extend.”

=====================================================================
REQUIRED OUTPUT STRUCTURE
=====================================================================
SECTION 1 — Complete Lesson Plan
Include the following in order:

1. Lesson Information  
   (Teacher, Lesson No., Duration, Level, Lesson Type, Learner Profile, Anticipated Problems)

2. Learning Objectives  
   - Write 2–3 measurable objectives beginning with “Students will be able to…”
   - Link each to Bloom’s levels (Understand, Apply, Analyze, Create).
   - Align objectives to rubric expectations.

3. Target Language  
   Create a two-column table:  
   Component | Content  
   Grammar / Structure |  
   Vocabulary |  
   Pronunciation Focus |  
   Functional Language |

4. Lesson Stages  
   Create a six-column table:  
   Stage | Timing | Purpose / Description | Teacher’s Role | Learners’ Role | Interaction Pattern  
   Ensure interaction patterns include (T→S, S↔S, Pair Work, Group Work, Whole Class).

   After the table, include a **Supporting Details** paragraph for each major stage.
   Supporting Details must describe:
   - Specific teacher and learner actions (“Teacher presents…”, “Cadets discuss…”)
   - Example sentences used in class
   - Teaching aids or materials (visuals, slides, boardwork, realia)
   - Formative checks and transitions
   - Differentiation for weaker and stronger cadets
   - Observable classroom behavior demonstrating understanding
   For "Good" targets: focus on clarity, pacing, and control.
   For "Outstanding" targets: include creativity, learner autonomy, and innovation.

5. Differentiation  
   Describe how weaker cadets receive structured support and stronger cadets are challenged with extension tasks.

6. Assessment & Feedback  
   Include formative and summative checks, peer or self-assessment, and exit tasks.

7. Reflection & Notes  
   Provide prompts that help the teacher reflect on lesson delivery, pacing, and student engagement.

=====================================================================
SECTION 2 — Observation Readiness Coaching Guide
=====================================================================
Provide mentoring advice under each rubric domain (1–9).

For each domain include:

Domain Name  
Rubric Check: Explain how this plan meets the “Good” or “Outstanding” descriptor.  
AI Mentor Comment: Provide one practical improvement or reflection point.

Do NOT include any “Summary of AI-Generated Guidance” lines.

=====================================================================
ADDITIONAL INTELLIGENCE
=====================================================================
- Infer CEFR level (A1–C1) and lesson type from uploaded materials.
- Apply Bloom’s Taxonomy verbs within objectives.
- Use official BAE terminology such as “cadets,” “SOP-4 compliance,” “formative check,” “timed stages,” and “learner-centred.”
- Demonstrate transitions, engagement, and classroom readiness.

=====================================================================
RUBRIC SELF-CHECK BEFORE OUTPUT
=====================================================================
Before finalizing, ensure:
1. All 9 domains are covered.
2. Each descriptor matches the chosen Target Rating.
3. All required headings and sub-sections exist.
4. Lesson Stages include Supporting Details paragraphs.
5. No “Summary” lines are present.
6. Output is structured, professional, and plain-text.

=====================================================================
STYLE RULES
=====================================================================
- Plain text only (no markdown, emojis, or code blocks).
- Use formal, readable English suitable for observation reports.
- Bold headings like “Domain Name”, “Rubric Check”, and “AI Mentor Comment”.
- Include blank lines between sections for clarity.
- Make the output export-ready for DOCX in landscape orientation.
"""

# ------------------------------------------------------------
# FILE TEXT EXTRACTION
# ------------------------------------------------------------
def extract_text_from_file(file):
    name = file.filename.lower()
    text = ""
    if name.endswith(".pdf"):
        reader = PdfReader(file)
        text = "\n".join([page.extract_text() or "" for page in reader.pages])
    elif name.endswith(".docx"):
        doc = Document(file)
        text = "\n".join(p.text for p in doc.paragraphs)
    elif name.endswith(".xlsx"):
        wb = load_workbook(file)
        for sheet in wb.worksheets:
            for row in sheet.iter_rows(values_only=True):
                text += " ".join(str(c) for c in row if c) + "\n"
    elif name.endswith((".png", ".jpg", ".jpeg")):
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            file.save(tmp.name)
            img = Image.open(tmp.name)
            text = pytesseract.image_to_string(img)
    else:
        text = file.read().decode("utf-8", errors="ignore")
    return text.strip()

# ------------------------------------------------------------
# STYLE UTILITIES
# ------------------------------------------------------------
def style_table_headers(table):
    hdr = table.rows[0]
    for cell in hdr.cells:
        shading = parse_xml(r'<w:shd {} w:fill="D9D9D9"/>'.format(nsdecls("w")))
        cell._tc.get_or_add_tcPr().append(shading)
        for p in cell.paragraphs:
            run = p.runs[0] if p.runs else p.add_run()
            run.font.bold = True
            run.font.size = Pt(10)

def autofit_columns(table, cm_width=3.5):
    for row in table.rows:
        for cell in row.cells:
            cell.width = Cm(cm_width)

# ------------------------------------------------------------
# MAIN ROUTE
# ------------------------------------------------------------
@app.route("/generate", methods=["POST"])
def generate_lesson_plan():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"error": "No file uploaded"}), 400

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

        # ---------------- AI CALL ----------------
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
        )

        lesson_text = response.choices[0].message.content.strip()

        # ---------------- CLEANUP ----------------
        lesson_text = re.sub(r"(?i)^.*summary of ai[- ]?generated guidance.*$", "", lesson_text, flags=re.MULTILINE)
        lesson_text = re.sub(r"\n{2,}", "\n", lesson_text).strip()

        # ---------------- DOCX GENERATION ----------------
        doc = Document()
        section = doc.sections[0]
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = section.page_height, section.page_width
        section.top_margin = section.bottom_margin = Inches(0.6)
        section.left_margin = section.right_margin = Inches(0.6)

        doc.add_heading("AI Lesson Plan — Observation Readiness Coach", level=0)
        doc.add_paragraph(f"Generated on: {timestamp}")
        doc.add_paragraph(f"Target Rating: {target_rating}")
        doc.add_paragraph("")

        current_table = None
        for line in lesson_text.split("\n"):
            line = line.strip()
            if not line:
                continue

            # ---- TABLE HANDLING ----
            if "|" in line:
                cols = [c.strip() for c in line.split("|")]
                if current_table is None:
                    current_table = doc.add_table(rows=1, cols=len(cols))
                    current_table.style = "Table Grid"
                    hdr = current_table.rows[0]
                    for i, txt in enumerate(cols):
                        hdr.cells[i].text = txt
                    style_table_headers(current_table)
                else:
                    row = current_table.add_row()
                    for i, txt in enumerate(cols):
                        row.cells[i].text = txt
                autofit_columns(current_table)
                continue

            # ---- PARAGRAPH HANDLING ----
            current_table = None
            p = doc.add_paragraph()
            run = p.add_run(line)

            heading_keywords = [
                "section", "lesson information", "learning objectives", "target language",
                "lesson stages", "supporting details", "differentiation", "assessment",
                "feedback", "reflection", "domain name", "rubric check",
                "ai mentor comment", "professional reflection", "observation readiness"
            ]
            if any(k in line.lower() for k in heading_keywords):
                run.font.bold = True
                run.font.size = Pt(11)
            else:
                run.font.size = Pt(10)
            p.paragraph_format.space_after = Pt(4)

        # ---------------- FOOTER ----------------
        doc.add_paragraph("")
        doc.add_paragraph("Generated by: AI Lesson Planner v5.0 — BAE Rubric Hybrid with Supporting Details")
        doc.add_paragraph(f"Instructor: {teacher_name}")
        doc.add_paragraph(f"Lesson Number: {lesson_number}")
        doc.add_paragraph(f"Date: {timestamp}")

        filename = f"Lesson_Plan_{teacher_name.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d_%H%M')}.docx"
        path = os.path.join(tempfile.gettempdir(), filename)
        doc.save(path)
        return send_file(path, as_attachment=True, download_name=filename)

    except Exception as e:
        print("Error:", e)
        return jsonify({"error": str(e)}), 500


@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "AI Lesson Planner v5.0 (StanEval Hybrid, Landscape) is running"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)

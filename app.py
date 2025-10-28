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
from docx.shared import RGBColor
import tempfile
from datetime import datetime


app = Flask(__name__)

# ✅ Enable CORS globally
CORS(app, supports_credentials=True)

@app.after_request
def after_request(response):
    """Ensure every response includes proper CORS headers."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Credentials"] = "true"
    return response


# ✅ Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# ------------------------------------------------------------
# BASIC ROUTES
# ------------------------------------------------------------
@app.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Lesson Planner API is running"}), 200

# ✅ Handle preflight (CORS) for /generate route
@app.route("/generate", methods=["OPTIONS"])
def generate_options():
    """Handle CORS preflight for the /generate route."""
    response = jsonify({"ok": True})
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response, 200

# ------------------------------------------------------------
# SYSTEM PROMPT — EXACT TEXT WITH NO ASTERISKS
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
- You prepare teachers for real formal observations; your lesson plans must show
  clear evidence of meeting each StanEval domain.

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
- Use verbs such as ensure, maintain, provide, follow up.

When Target Rating = “Outstanding”:
- Use ambitious, creative phrasing showing learner autonomy.
- Use verbs such as inspire, facilitate, empower, extend.

=====================================================================
REQUIRED OUTPUT STRUCTURE
=====================================================================
SECTION 1 — Complete Lesson Plan
Include the following in order:

1. Lesson Information
   Teacher, Lesson No., Duration, Level, Lesson Type, Learner Profile, Anticipated Problems

2. Learning Objectives
   - Write 2–3 measurable objectives beginning with Students will be able to …
   - Link each to Bloom’s levels Understand, Apply, Analyze, Create.
   - Align objectives to rubric expectations.

3. Target Language
   Provide a two-column table:
   Component | Content
   Grammar / Structure |
   Vocabulary |
   Pronunciation Focus |
   Functional Language |

4. Lesson Stages
   Provide a six-column table:
   Stage | Timing | Purpose / Description | Teacher’s Role | Learners’ Role | Interaction Pattern
   Ensure interaction patterns include T→S, S↔S, Pair Work, Group Work, Whole Class.

   After the table, include a Supporting Details paragraph for each major stage.
   Supporting Details must describe:
   - Specific teacher and learner actions such as Teacher presents …, Cadets discuss …
   - Example sentences used in class
   - Teaching aids or materials visuals, slides, boardwork, realia
   - Formative checks and transitions
   - Differentiation for weaker and stronger cadets
   - Observable classroom behavior demonstrating understanding
   For Good targets: focus on clarity, pacing, and control.
   For Outstanding targets: include creativity, learner autonomy, and innovation.

5. Differentiation
   Describe how weaker cadets receive structured support and stronger cadets are challenged with extension tasks.

6. Assessment & Feedback
   Include formative and summative checks, peer or self-assessment, and exit tasks.

7. Reflection & Notes
   Provide prompts that help the teacher reflect on lesson delivery, pacing, and student engagement.

=====================================================================
SECTION 2 — Observation Readiness Coaching Guide
=====================================================================
Provide mentoring advice under each rubric domain 1–9.

For each domain include:

Domain Name
Rubric Check: Explain how this plan meets the Good or Outstanding descriptor.
AI Mentor Comment: Provide one practical improvement or reflection point.

Do NOT include any Summary of AI-Generated Guidance lines.

=====================================================================
ADDITIONAL INTELLIGENCE
=====================================================================
- Infer CEFR level A1–C1 and lesson type from uploaded materials.
- Apply Bloom’s Taxonomy verbs within objectives.
- Use official BAE terminology such as cadets, SOP-4 compliance, formative check, timed stages, and learner-centred.
- Demonstrate transitions, engagement, and classroom readiness.

=====================================================================
RUBRIC SELF-CHECK BEFORE OUTPUT
=====================================================================
Before finalizing, ensure:
1. All 9 domains are covered.
2. Each descriptor matches the chosen Target Rating.
3. All required headings and sub-sections exist.
4. Lesson Stages include Supporting Details paragraphs.
5. No Summary lines are present.
6. Output is structured, professional, and plain-text.

=====================================================================
STYLE RULES
=====================================================================
- Plain text only no markdown or code blocks.
- Never use asterisks at all. Do not output * or ** anywhere.
- Use formal, readable English suitable for observation reports.
- Write headings as plain text words only; do not surround with symbols.
- Include blank lines between sections for clarity.
- Make the output export-ready for DOCX in landscape orientation.
"""

# ------------------------------------------------------------
# FILE TEXT EXTRACTION (PDF ONLY)
# ------------------------------------------------------------
def extract_text_from_file(file):
    name = file.filename.lower()
    if not name.endswith(".pdf"):
        return ""
    reader = PdfReader(file)
    text = "\n".join([(page.extract_text() or "") for page in reader.pages])
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
            run.bold = True
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
            return jsonify({"error": "Could not extract text from PDF"}), 400

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
        # Remove any accidental "summary" lines
        lesson_text = re.sub(r"(?i)^.*summary of ai[- ]?generated guidance.*$", "", lesson_text, flags=re.MULTILINE)
        # Collapse excess newlines
        lesson_text = re.sub(r"\n{2,}", "\n", lesson_text).strip()
        # STRICT RULE: strip ALL asterisks from the model output
        lesson_text = lesson_text.replace("*", "")

        # ---------------- DOCX GENERATION ----------------
        doc = Document()
        section = doc.sections[0]
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width, section.page_height = section.page_height, section.page_width
        section.left_margin = Inches(0.7)
        section.right_margin = Inches(0.7)
        section.top_margin = Inches(0.6)
        section.bottom_margin = Inches(0.6)

        style = doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(11)

        doc.add_heading("AI Lesson Plan — Observation Readiness Coach", level=0)
        doc.add_paragraph(f"Generated on: {timestamp}")
        doc.add_paragraph(f"Target Rating: {target_rating}")
        doc.add_paragraph("")

        current_table = None
        current_table_cols = 0
        inside_section2 = False

        lines = lesson_text.split("\n")
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            i += 1
            if not line:
                continue

            # Page break when SECTION 2 starts
            if "SECTION 2" in line.upper() and not inside_section2:
                current_table = None
                current_table_cols = 0
                doc.add_page_break()
                inside_section2 = True
                continue

            # Section headers
            if re.match(r"^section\s+\d+", line, re.I):
                current_table = None
                current_table_cols = 0
                p = doc.add_paragraph(line.upper())
                run = p.runs[0]
                run.bold = True
                run.font.size = Pt(14)
                run.font.color.rgb = RGBColor(255, 255, 255)
                shading = parse_xml(r'<w:shd {} w:fill="003366"/>'.format(nsdecls("w")))
                p._p.get_or_add_pPr().append(shading)
                p.alignment = 1  # center
                doc.add_paragraph()
                continue

            # Domain blocks (Section 2) — robust label/value capture
            if line.lower().startswith("domain name"):
                current_table = doc.add_table(rows=3, cols=2)
                current_table_cols = 2
                current_table.style = "Table Grid"
                for column in current_table.columns:
                    for cell in column.cells:
                        cell.width = Inches(3.5)

                # Left labels
                current_table.rows[0].cells[0].text = "Domain Name"
                current_table.rows[1].cells[0].text = "Rubric Check"
                current_table.rows[2].cells[0].text = "AI Mentor Comment"
                for r in range(3):
                    lbl_run = current_table.rows[r].cells[0].paragraphs[0].runs[0]
                    lbl_run.bold = True
                    current_table.rows[r].cells[0]._tc.get_or_add_tcPr().append(
                        parse_xml(r'<w:shd {} w:fill="D9D9D9"/>'.format(nsdecls("w")))
                    )

                # Helper to read value after a label (same line after ':' or next non-empty line)
                def read_value_from_line_or_next(current_line, expected_prefix):
                    val = re.sub(rf"^{expected_prefix}[:]*", "", current_line, flags=re.I).strip()
                    if val:
                        return val
                    nonlocal i
                    while i < len(lines) and not lines[i].strip():
                        i += 1
                    if i < len(lines):
                        v = lines[i].strip()
                        i += 1
                        return v
                    return ""

                # Domain Name value
                domain_val = read_value_from_line_or_next(line, "domain name")
                current_table.rows[0].cells[1].text = domain_val

                # Rubric Check value
                rubric_val = ""
                if i < len(lines):
                    peek = lines[i].strip()
                    if peek.lower().startswith("rubric check"):
                        i += 1
                        rubric_val = read_value_from_line_or_next(peek, "rubric check")
                    else:
                        rubric_val = peek
                        i += 1
                current_table.rows[1].cells[1].text = rubric_val

                # AI Mentor Comment value
                mentor_val = ""
                if i < len(lines):
                    peek = lines[i].strip()
                    if peek.lower().startswith("ai mentor comment"):
                        i += 1
                        mentor_val = read_value_from_line_or_next(peek, "ai mentor comment")
                    else:
                        mentor_val = peek
                        i += 1
                current_table.rows[2].cells[1].text = mentor_val

                current_table = None
                current_table_cols = 0
                continue

            # Table rows (pipe-separated)
            if "|" in line:
                cols = [c.strip() for c in line.split("|")]
                if current_table is None:
                    current_table = doc.add_table(rows=1, cols=len(cols))
                    current_table_cols = len(cols)
                    current_table.style = "Table Grid"
                    hdr_cells = current_table.rows[0].cells
                    for j, text in enumerate(cols):
                        hdr_cells[j].text = text
                        for p in hdr_cells[j].paragraphs:
                            run = p.runs[0] if p.runs else p.add_run()
                            run.bold = True
                            run.font.size = Pt(10)
                    for cell in hdr_cells:
                        shading = parse_xml(r'<w:shd {} w:fill="E6E6FA"/>'.format(nsdecls("w")))
                        cell._tc.get_or_add_tcPr().append(shading)
                else:
                    if len(cols) < current_table_cols:
                        cols += [""] * (current_table_cols - len(cols))
                    elif len(cols) > current_table_cols:
                        cols = cols[:current_table_cols]
                    row = current_table.add_row()
                    for j, text in enumerate(cols):
                        row.cells[j].text = text
                continue

            # Normal headings (explicit keywords)
            if any(k in line.lower() for k in [
                "lesson information", "learning objectives", "lesson stages", "supporting details",
                "differentiation", "assessment", "reflection & notes"
            ]):
                current_table = None
                current_table_cols = 0
                p = doc.add_paragraph(line)
                run = p.runs[0]
                run.bold = True
                run.font.size = Pt(12)
                p.paragraph_format.space_before = Pt(8)
                p.paragraph_format.space_after = Pt(6)
                continue

            # Default paragraph (no inline asterisks allowed; already stripped)
            current_table = None
            current_table_cols = 0
            p = doc.add_paragraph(line)
            p.paragraph_format.line_spacing = 1.15
            p.paragraph_format.space_after = Pt(4)

        # Footer
        footer = doc.sections[0].footer
        footer_para = footer.paragraphs[0]
        footer_para.text = "AI Lesson Planner — BAE StanEval Hybrid | © 2025 Kaled Alenezi"
        footer_para.alignment = 1
        footer_para.runs[0].font.size = Pt(8)

        # Save and return
        output = tempfile.NamedTemporaryFile(delete=False, suffix=".docx")
        doc.save(output.name)
        output.seek(0)
        return send_file(output.name, as_attachment=True, download_name="BAE_Lesson_Plan.docx")

    except Exception as e:
        print("❌ ERROR in /generate:", e)
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    # If deploying on Railway/Gunicorn, this block is ignored (Gunicorn imports the app)
    app.run(host="0.0.0.0", port=5000)

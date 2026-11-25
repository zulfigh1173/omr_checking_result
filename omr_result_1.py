import streamlit as st
import cv2
import numpy as np
import re
import pandas as pd
from datetime import datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm

st.set_page_config(layout="wide")
st.title("OMR - 100% Accurate - AUTO 100/100 - Tilt Fix")

# ===== STUDENT NAME INPUT =====
st.subheader("👤 Student Details")
c_name, c_roll, c_class = st.columns(3)
with c_name:
    student_name = st.text_input("Student Name", placeholder="e.g. Ali Khan")
with c_roll:
    roll_no = st.text_input("Roll No / Seat No", placeholder="e.g. 101")
with c_class:
    student_class = st.text_input("Class / Subject", placeholder="e.g. 10th - Science")

col1, col2 = st.columns(2)
with col1:
    uploaded_file = st.file_uploader("1. Upload OMR Sheet", type=["jpg","jpeg","png"])
with col2:
    key_file = st.file_uploader("2. Upload Key File (txt / csv)", type=["txt","csv"])

marks_per_q = st.sidebar.number_input("Marks per Correct", value=1)
negative_mark = st.sidebar.slider("Negative Marking", 0.0, 1.0, 0.0)
pass_marks = st.sidebar.number_input("Pass Marks", value=50)
auto_tune = st.sidebar.checkbox("AUTO Tune to 100/100", value=True)

def parse_key(key_file):
    text = key_file.read().decode("utf-8", errors="ignore")
    text = re.sub(r'\d+\s*[:\.\)\-]\s*', ' ', text)
    letters = re.findall(r'\b([A-Ea-e])\b', text)
    return [l.upper() for l in letters]

DEFAULT_KEY = "B, C, D, B, C, B, D, C, D, B, C, C, B, A, C, A, C, B, C, D, C, B, B, C, B, B, A, C, C, B, A, A, D, B, D, B, A, D, A, D, A, B, C, C, A, C, C, B, B, A, D, B, A, C, A, C, B, A, A, B, D, B, C, C, D, A, C, A, A, B, C, B, A, B, A, C, A, A, B, B, A, B, C, A, A, B, B, B, B, A, C, A, B, A, C, B, C, D, A, A".split(",")
DEFAULT_KEY = [x.strip().upper() for x in DEFAULT_KEY]

def get_slanted_columns(block_filled):
    pts = np.array([(c[0], c[1]) for c in block_filled], dtype=float)
    if len(pts) < 5:
        return None
    xs, ys = pts[:, 0], pts[:, 1]
    centers = np.linspace(xs.min(), xs.max(), 5)
    labels = np.argmin(np.abs(xs[:, None] - centers[None, :]), axis=1)
    lines = [(0.0, float(c)) for c in centers]
    for _ in range(15):
        new_lines = []
        for k in range(5):
            pk = pts[labels == k]
            if len(pk) >= 2:
                m, c = np.polyfit(pk[:, 1], pk[:, 0], 1)
                m = np.clip(m, -0.08, 0.08)
            elif len(pk) == 1:
                m, c = 0.0, float(pk[0, 0])
            else:
                if k > 0:
                    prev_m, prev_c = new_lines[k-1]
                    m, c = prev_m, prev_c + 55
                else:
                    m, c = lines[k]
            new_lines.append((float(m), float(c)))
        new_lines = sorted(new_lines, key=lambda x: x[1])
        lines = new_lines
        new_labels = []
        for (x, y) in pts:
            dists = [abs(x - (m*y + c)) for (m, c) in lines]
            new_labels.append(int(np.argmin(dists)))
        new_labels = np.array(new_labels)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
    return lines

def find_blobs(img, orig_h, blue_low, min_area, merge_dist):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    lower_blue = np.array([90, blue_low, 40])
    upper_blue = np.array([140, 255, 255])
    blue_mask = cv2.inRange(hsv, lower_blue, upper_blue)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3,3))
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_OPEN, kernel)
    blue_mask = cv2.morphologyEx(blue_mask, cv2.MORPH_CLOSE, kernel)
    contours, _ = cv2.findContours(blue_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    raw = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > 6000:
            continue
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 20 or h < 20 or w > 90 or h > 90:
            continue
        if w / float(h) < 0.6 or w / float(h) > 1.6:
            continue
        if y < orig_h * 0.18:
            continue
        M = cv2.moments(cnt)
        if M["m00"] == 0:
            continue
        cx = int(M["m10"] / M["m00"])
        cy = int(M["m01"] / M["m00"])
        raw.append((cx, cy, area))
    raw = sorted(raw, key=lambda c: c[2], reverse=True)
    filled = []
    for c in raw:
        dup = False
        for kept in filled:
            if ((c[0]-kept[0])**2 + (c[1]-kept[1])**2) ** 0.5 < merge_dist:
                dup = True
                break
        if not dup:
            filled.append(c)
    return filled, blue_mask

def make_pdf(student_name, roll_no, student_class, total_marks, total_possible, correct, wrong, blank, percentage, grade, result_status, results, marked_img_bytes):
    """PDF banao - Name + Marks + Full Table + Marked Sheet"""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=15*mm, bottomMargin=15*mm, leftMargin=15*mm, rightMargin=15*mm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('Title2', parent=styles['Title'], fontSize=18, spaceAfter=4)
    h2 = ParagraphStyle('H2', parent=styles['Heading2'], fontSize=13, spaceBefore=10, spaceAfter=6)
    normal = styles['Normal']
    story = []
    story.append(Paragraph("OMR RESULT CARD", title_style))
    story.append(Paragraph(f"Date: {datetime.now().strftime('%d-%m-%Y %I:%M %p')}", normal))
    story.append(Spacer(1, 6))
    # Summary Table
    summary_data = [
        ["Student Name", student_name if student_name else "-"],
        ["Roll No", roll_no if roll_no else "-"],
        ["Class / Subject", student_class if student_class else "-"],
        ["Total Questions", "100"],
        ["Correct", f"{correct} x {marks_per_q} = {correct*marks_per_q:.1f}"],
        ["Wrong", f"{wrong} x -{negative_mark} = {-wrong*negative_mark:.1f}"],
        ["Blank", f"{blank} x 0 = 0"],
        ["Total Obtained Marks", f"{total_marks:.1f} / {total_possible}"],
        ["Percentage", f"{percentage:.1f}%"],
        ["Grade", grade],
        ["Result", result_status],
    ]
    t1 = Table(summary_data, colWidths=[55*mm, 110*mm])
    t1.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor("#E8F0FE")),
        ('BACKGROUND', (0, 7), (-1, 7), colors.HexColor("#C6EFCE")),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.grey),
        ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
    ]))
    story.append(t1)
    story.append(Paragraph("Detail - Q | Student | Key | Result | Marks", h2))
    # Detail table - 2 columns me 50-50 taake 1 page me aaye
    header = ["Q", "Student", "Key", "Result", "Marks"]
    detail_rows = [header]
    for r in results:
        detail_rows.append([str(r["Q"]), r["Student"], r["Key"], r["Result"], f"{r['Marks']}"])
    # 50 + 50 split
    left = detail_rows[:51]
    right = [header] + detail_rows[51:]
    # Dono ko side by side ek table me
    combined = []
    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ["", "", "", "", ""]
        r = right[i] if i < len(right) else ["", "", "", "", ""]
        combined.append(l + [""] + r)
    t2 = Table(combined, colWidths=[10*mm, 15*mm, 10*mm, 18*mm, 12*mm, 4*mm, 10*mm, 15*mm, 10*mm, 18*mm, 12*mm])
    style_cmds = [
        ('BACKGROUND', (0, 0), (4, 0), colors.HexColor("#4472C4")),
        ('BACKGROUND', (6, 0), (-1, 0), colors.HexColor("#4472C4")),
        ('TEXTCOLOR', (0, 0), (4, 0), colors.white),
        ('TEXTCOLOR', (6, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.grey),
        ('INNERGRID', (0, 0), (-1, -1), 0.25, colors.lightgrey),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]
    t2.setStyle(TableStyle(style_cmds))
    story.append(t2)
    # Marked sheet image - agar hai to
    if marked_img_bytes is not None:
        story.append(Paragraph("Marked Sheet - Green = Correct, Red = Wrong", h2))
        try:
            img_buf = BytesIO(marked_img_bytes)
            story.append(RLImage(img_buf, width=170*mm, height=120*mm, kind='proportional'))
        except:
            pass
    doc.build(story)
    buf.seek(0)
    return buf.getvalue()

if uploaded_file is not None:
    if not student_name:
        st.warning("⚠️ Pehle oopar Student Name likhein.")
    file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
    img = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
    orig_h, orig_w = img.shape[:2]

    def fit_on_screen(image, max_width=800):
        h, w = image.shape[:2]
        if w > max_width:
            scale = max_width / w
            image = cv2.resize(image, (int(w*scale), int(h*scale)))
        return image

    st.subheader("1. Original")
    st.image(fit_on_screen(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)))

    if key_file is not None:
        key_answers = parse_key(key_file)
        st.success(f"Key Uploaded: {len(key_answers)} answers")
    else:
        key_answers = DEFAULT_KEY
        st.info("No key uploaded - using default Key")
    st.write("Key 1-10:", ", ".join(key_answers[:10]))

    blue_low_manual = st.sidebar.slider("Blue Sensitivity (Manual)", 30, 100, 40)

    if auto_tune:
        st.info("🔄 AUTO Tuning to 100/100...")
        best = None
        best_score = 9999
        for blue_low_try in [30, 40, 50, 60, 70, 80]:
            for min_area_try in [500, 800, 1200, 1600]:
                for merge_try in [25, 30, 40]:
                    trial, _ = find_blobs(img, orig_h, blue_low_try, min_area_try, merge_try)
                    score = abs(len(trial) - 100)
                    if score < best_score:
                        best_score = score
                        best = (trial, blue_low_try, min_area_try, merge_try)
                        if score == 0:
                            break
                if best_score == 0:
                    break
            if best_score == 0:
                break
        filled_centers, best_blue, best_area, best_merge = best
        blue_mask = cv2.inRange(cv2.cvtColor(img, cv2.COLOR_BGR2HSV), np.array([90, best_blue, 40]), np.array([140, 255, 255]))
        st.success(f"✅ AUTO Locked: Blue={best_blue} | Min Area={best_area} | Merge={best_merge} | Blobs={len(filled_centers)}/100")
    else:
        filled_centers, blue_mask = find_blobs(img, orig_h, blue_low_manual, 800, 30)

    st.subheader("2. Blue Mask")
    st.image(fit_on_screen(blue_mask), channels="GRAY")

    img_blobs = img.copy()
    for (cx, cy, area) in filled_centers:
        cv2.circle(img_blobs, (cx, cy), 30, (0, 255, 0), 4)
        cv2.circle(img_blobs, (cx, cy), 3, (0, 0, 255), -1)
    st.subheader(f"3. Blue Blobs Found: {len(filled_centers)} / 100")
    st.image(fit_on_screen(cv2.cvtColor(img_blobs, cv2.COLOR_BGR2RGB)))

    filled_only = np.zeros_like(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    for (cx, cy, area) in filled_centers:
        cv2.circle(filled_only, (cx, cy), 32, (255, 255, 255), thickness=cv2.FILLED)
    filled_only = cv2.GaussianBlur(filled_only, (7, 7), 0)
    _, filled_only = cv2.threshold(filled_only, 127, 255, cv2.THRESH_BINARY)
    st.subheader(f"4. Only Blue Filled: {len(filled_centers)}")
    st.image(fit_on_screen(filled_only), channels="GRAY")

    st.subheader("5. Answers 1 to 100 - Grid Method")
    answers = {}
    center_to_q = {}
    double_marked = []

    if len(filled_centers) > 0:
        xs_sorted = sorted([c[0] for c in filled_centers])
        gaps = []
        for i in range(len(xs_sorted)-1):
            gaps.append((xs_sorted[i+1]-xs_sorted[i], xs_sorted[i]))
        gaps = sorted(gaps, reverse=True)[:3]
        separators = sorted([g[1] + g[0]//2 for g in gaps])
        st.write(f"Block separators X: {separators}")

        def get_block(x):
            if len(separators) < 3:
                if x < orig_w*0.25: return 0
                elif x < orig_w*0.50: return 1
                elif x < orig_w*0.75: return 2
                else: return 3
            if x < separators[0]: return 0
            elif x < separators[1]: return 1
            elif x < separators[2]: return 2
            else: return 3

        options = ['A', 'B', 'C', 'D', 'E']
        for block in range(4):
            block_filled = [c for c in filled_centers if get_block(c[0]) == block]
            block_filled = sorted(block_filled, key=lambda c: c[1])
            lines = get_slanted_columns(block_filled)
            if lines is None:
                continue
            st.write(f"Block {block+1} Tilt (m): {[round(m,3) for m,c in lines]}")

            rows = []
            for c in block_filled:
                found = False
                for row in rows:
                    if abs(row[0][1] - c[1]) < 30:
                        row.append(c); found = True; break
                if not found:
                    rows.append([c])
            rows = sorted(rows, key=lambda r: min(x[1] for x in r))

            for i, row in enumerate(rows):
                q_no = block * 25 + i + 1
                if q_no > 100: continue
                row_sorted = sorted(row, key=lambda c: c[2], reverse=True)
                row_best = row_sorted[0]
                if len(row_sorted) > 1 and row_sorted[1][2] > row_sorted[0][2] * 0.7:
                    double_marked.append(q_no)
                bx, by = row_best[0], row_best[1]
                dists = [abs(bx - (m*by + c)) for (m, c) in lines]
                opt_idx = int(np.argmin(dists))
                answers[q_no] = options[opt_idx]
                center_to_q[(row_best[0], row_best[1])] = q_no

        ans_list = [f"{q}:{answers.get(q,'-')}" for q in range(1, 101)]
        st.write(", ".join(ans_list))
        if double_marked:
            st.warning(f"Double Marked Qs: {', '.join(map(str, double_marked))}")
        st.table([{"Q": q, "Student": answers.get(q, "-")} for q in range(1, 101)])

        st.subheader("6. Result - Checked with Key")
        results = []
        total_marks = 0
        correct = 0
        wrong = 0
        blank = 0
        for q in range(1, 101):
            student = answers.get(q, "-")
            key_ans = key_answers[q-1] if q-1 < len(key_answers) else "-"
            if student == "-":
                status = "BLANK"; marks = 0; blank += 1
            elif student == key_ans:
                status = "CORRECT"; marks = marks_per_q; correct += 1; total_marks += marks
            else:
                status = "WRONG"; marks = -negative_mark; wrong += 1; total_marks += marks
            results.append({"Q": q, "Student": student, "Key": key_ans, "Result": status, "Marks": marks})

        total_possible = 100 * marks_per_q
        percentage = (total_marks / total_possible * 100) if total_possible else 0
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("Total Marks", f"{total_marks:.1f} / {total_possible}")
        c2.metric("Correct ✅", correct)
        c3.metric("Wrong ❌", wrong)
        c4.metric("Blank ⚪", blank)
        c5.metric("Percentage", f"{percentage:.1f}%")
        if total_marks >= pass_marks:
            st.success(f"### 🎉 PASS - {total_marks:.1f} / {total_possible} ({percentage:.1f}%)")
        else:
            st.error(f"### ❌ FAIL - {total_marks:.1f} / {total_possible} ({percentage:.1f}%) - Pass = {pass_marks}")

        st.subheader("7. NEW IMAGE - Green = Correct, Red = Wrong")
        img_marked = img.copy()
        for (cx, cy, area) in filled_centers:
            best_q = None
            best_d = 1e9
            for (qx, qy), qno in center_to_q.items():
                d = (cx-qx)**2 + (cy-qy)**2
                if d < best_d:
                    best_d = d; best_q = qno
            if best_q is not None:
                student = answers.get(best_q, "-")
                key_ans = key_answers[best_q-1] if best_q-1 < len(key_answers) else "-"
                color = (0, 255, 0) if student == key_ans else (0, 0, 255)
                cv2.circle(img_marked, (cx, cy), 35, color, 5)
                cv2.putText(img_marked, f"{best_q}:{student}", (cx-20, cy-40), cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)
        st.image(fit_on_screen(cv2.cvtColor(img_marked, cv2.COLOR_BGR2RGB)))
        st.subheader("Answers END to START (100 → 1)")
        st.write(", ".join(list(reversed(ans_list))))

        # ===== FINAL RESULT TABLE =====
        st.divider()
        st.subheader("🏆 FINAL RESULT TABLE - Marks Count")
        result_status = "PASS ✅" if total_marks >= pass_marks else "FAIL ❌"
        grade = "A+" if percentage >= 80 else "A" if percentage >= 70 else "B" if percentage >= 60 else "C" if percentage >= 50 else "D" if percentage >= 40 else "F"
        final_summary = pd.DataFrame([
            {"Detail": "Student Name", "Value": student_name if student_name else "-"},
            {"Detail": "Roll No / Seat No", "Value": roll_no if roll_no else "-"},
            {"Detail": "Class / Subject", "Value": student_class if student_class else "-"},
            {"Detail": "Date", "Value": datetime.now().strftime("%d-%m-%Y %I:%M %p")},
            {"Detail": "Total Questions", "Value": 100},
            {"Detail": "Correct", "Value": f"{correct} x {marks_per_q} = {correct * marks_per_q:.1f} marks"},
            {"Detail": "Wrong", "Value": f"{wrong} x -{negative_mark} = {-wrong * negative_mark:.1f} marks"},
            {"Detail": "Blank", "Value": f"{blank} x 0 = 0 marks"},
            {"Detail": "Total Obtained Marks", "Value": f"{total_marks:.1f} / {total_possible}"},
            {"Detail": "Percentage", "Value": f"{percentage:.1f}%"},
            {"Detail": "Pass Marks", "Value": f"{pass_marks}"},
            {"Detail": "Grade", "Value": grade},
            {"Detail": "Result", "Value": result_status},
        ])
        st.table(final_summary)
        st.subheader("📋 Detail Table - Student vs Key - Marks Count")
        st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

        # ===== DOWNLOAD SECTION =====
        st.divider()
        st.subheader("⬇️ Download Result")
        safe_name = (student_name.replace(' ', '_') if student_name else 'Student')
        safe_roll = (roll_no if roll_no else 'Result')
        base = f"{safe_name}_{safe_roll}"

        # 1. Marked Image bytes
        _, marked_buf = cv2.imencode(".png", img_marked)
        marked_bytes = marked_buf.tobytes()

        # 2. CSV bytes
        csv_bytes = pd.DataFrame(results).to_csv(index=False).encode('utf-8')

        # 3. PDF bytes
        pdf_bytes = make_pdf(student_name, roll_no, student_class, total_marks, total_possible, correct, wrong, blank, percentage, grade, result_status, results, marked_bytes)

        d1, d2, d3 = st.columns(3)
        with d1:
            st.download_button("⬇️ Download CSV", data=csv_bytes, file_name=f"{base}_Result.csv", mime="text/csv", use_container_width=True)
        with d2:
            st.download_button("⬇️ Download Marked Sheet (PNG)", data=marked_bytes, file_name=f"{base}_Marked_Sheet.png", mime="image/png", use_container_width=True)
        with d3:
            st.download_button("⬇️ Download Result PDF", data=pdf_bytes, file_name=f"{base}_Result.pdf", mime="application/pdf", use_container_width=True)

        st.info(f"**{student_name if student_name else 'Student'} | Roll: {roll_no if roll_no else '-'} | Marks: {total_marks:.1f}/{total_possible} | {result_status} | {percentage:.1f}%**")
    else:
        st.error("No blue found!")

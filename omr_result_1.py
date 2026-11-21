import streamlit as st
from PIL import Image, ImageDraw
import csv, io, re

st.set_page_config(page_title="OMR Paper Checker", layout="wide")
st.title("📝 OMR Paper Checker ✅")
st.markdown("**Easy to Use | Auto Total | Smart Key | Half Fill Option | All Filled Ignore**")

# ---------- SMART KEY PARSING ----------
def parse_key_smart(content):
    content = content.replace("\n", ",").replace("\r", ",").replace(";", ",").replace("|", ",")
    tokens = [t.strip() for t in content.split(",") if t.strip()!=""]
    parsed = []
    for t in tokens:
        letters = re.findall(r'[A-E]', t.upper())
        if letters:
            parsed.append(letters[-1])
    return parsed

# ---------- STEP 1 - KEY ----------
st.subheader("1⃣ Answer Key - First Give Key")
st.write("Any format works: `B,A,C,D,A` or `Q1: B, Q2: A`")
key_file = st.file_uploader("Key File (key.txt)", type=["txt","csv"], key="keyfile")
key_input = st.text_input("Or Write Key Here", value="B,A,C,D,A")

answer_key = None
key_source = ""
key_file_parsed = None

if key_file is not None:
    try:
        content = key_file.read().decode('utf-8')
        key_file_parsed = parse_key_smart(content)
        answer_key = key_file_parsed
        key_source = f"File: {key_file.name}"
    except Exception as e:
        st.error(f"Key file error: {e}")
elif key_input.strip() != "":
    answer_key = parse_key_smart(key_input)
    key_source = "Text box"

# ---------- AUTO TOTAL QUESTIONS ----------
if "total_q" not in st.session_state:
    st.session_state.total_q = 5

if key_file_parsed is not None and len(key_file_parsed) > 0:
    if st.session_state.total_q != len(key_file_parsed):
        st.session_state.total_q = len(key_file_parsed)
        st.rerun()

# ---------- SETTINGS - EASY ENGLISH NAMES ----------
st.sidebar.header("⚙ Settings")
total_q = st.sidebar.number_input("Total Questions (Auto from Key)", min_value=1, max_value=200, key="total_q")
options_per_q = st.sidebar.selectbox("Options Per Question", [4, 5], index=0)
negative = st.sidebar.number_input("Minus Marks", value=0.25, step=0.25)
correct_marks = st.sidebar.number_input("Marks for Correct", value=1.0, step=0.5)
pass_pct = st.sidebar.number_input("Pass Percentage", value=40)
option_letters = ['A','B','C','D','E'][:options_per_q]

# ---------- BLANK OPTION - EASY NAME ----------
blank_mode = st.sidebar.radio(
    "What to do with Blank?",
    ["Blank = No Marks", "Blank = Wrong"],
    index=0
)
if "Wrong" in blank_mode:
    blank_handle = "wrong"
else:
    blank_handle = "keep"

# ---------- HALF FILL OPTION - EASY NAME ----------
st.sidebar.markdown("---")
half_mode = st.sidebar.radio(
    "Half Filled Bubble?",
    ["Half Filled = Accept", "Half Filled = Reject"],
    index=0
)
if "Reject" in half_mode:
    fill_threshold = 1500
    half_handle = "reject"
else:
    fill_threshold = 800
    half_handle = "accept"

st.sidebar.info(f"Threshold: {fill_threshold} dark pixels")
st.sidebar.success("✅ No cv2 | No numpy | No pandas")

# ---------- KEY CHECK ----------
if answer_key:
    if len(answer_key) != total_q:
        st.warning(f"Key has {len(answer_key)}, Total is {total_q}.")
        answer_key = None
    else:
        st.success(f"✅ Key OK ({key_source}): {','.join(answer_key)} | Total Questions Auto Set: {total_q}")

# ---------- CROP - EASY NAME ----------
st.subheader("2⃣ Crop Photo (If Needed)")
c1,c2,c3,c4 = st.columns(4)
top_cut = c1.slider("Top Cut %", 0, 50, 0)
bottom_cut = c2.slider("Bottom Cut %", 0, 50, 0)
left_cut = c3.slider("Left Cut %", 0, 50, 0)
right_cut = c4.slider("Right Cut %", 0, 50, 0)

# ---------- CHECKING LOGIC ----------
def check_accurate(pil_img, answer_key, total_q, options_per_q, top_cut, bottom_cut, left_cut, right_cut, blank_handle, fill_threshold, half_handle):
    img = pil_img.convert("L")
    w,h = img.size
    left = int(w*left_cut/100); upper = int(h*top_cut/100)
    right = int(w*(100-right_cut)/100); lower = int(h*(100-bottom_cut)/100)
    if right>left and lower>upper:
        img = img.crop((left,upper,right,lower))
    img = img.resize((options_per_q*100, total_q*100))
    px = img.load()

    results=[]; correct=wrong=blank=0; double_mark=0; full_covered=0; half_rejected=0
    annotated = img.convert("RGB")
    draw = ImageDraw.Draw(annotated)

    for q in range(total_q):
        dark_list=[]
        for o in range(options_per_q):
            x0=o*100; y0=q*100
            dark=0; total_px=0
            for yy in range(y0+20, y0+80):
                for xx in range(x0+20, x0+80):
                    total_px+=1
                    if px[xx,yy] < 170:
                        dark+=1
            dark_list.append(dark)

        filled = [i for i,d in enumerate(dark_list) if d > fill_threshold]
        max_dark = max(dark_list)
        bubbled_idx = dark_list.index(max_dark)
        is_half = 800 < max_dark <= 1500

        # ---- ALL FILLED = IGNORE ----
        if len(filled) == options_per_q:
            ans="Blank"; blank+=1; full_covered+=1; res="All Filled - Ignore"; color=(128,128,128)
            x0=0; y0=q*100
            draw.rectangle([x0+10,y0+10,x0+options_per_q*100-10,y0+90], outline=color, width=4)
            draw.text((x0+10,y0+30), res, fill=color)

        # ---- HALF FILLED = REJECT ----
        elif half_handle == "reject" and is_half and len(filled)==0:
            ans="Blank"; blank+=1; half_rejected+=1; res="Half Filled - Reject"; color=(255,165,0)
            x0=bubbled_idx*100; y0=q*100
            draw.rectangle([x0+10,y0+10,x0+90,y0+90], outline=color, width=4)
            draw.text((x0+95,y0+30), "Half - Reject", fill=color)

        elif len(filled)==0:
            if blank_handle == "wrong":
                ans="Blank"; blank+=1; wrong+=1; res="Blank - Wrong"; color=(255,0,0)
            else:
                ans="Blank"; blank+=1; res="Blank"; color=(255,165,0)

        elif len(filled)>=2:
            ans=option_letters[bubbled_idx]; wrong+=1; res="Double Mark - Wrong"; color=(255,0,0); double_mark+=1
        else:
            ans=option_letters[bubbled_idx]
            if ans==answer_key[q]:
                correct+=1; res="Correct"; color=(0,180,0)
            else:
                wrong+=1; res="Wrong"; color=(255,0,0)

        results.append({"Q":q+1,"Key":answer_key[q],"Student":ans,"Result":res,"DarkPixels":dark_list})
        if ans!="Blank" and len(filled) != options_per_q and not (half_handle=="reject" and is_half and len(filled)==0):
            x0=bubbled_idx*100; y0=q*100
            draw.rectangle([x0+10,y0+10,x0+90,y0+90], outline=color, width=4)
            draw.text((x0+95,y0+30), res, fill=color)

    score = correct*correct_marks - wrong*negative
    total_marks = total_q*correct_marks
    perc = (score/total_marks*100) if total_marks>0 else 0
    status = "PASS ✅" if perc >= pass_pct else "FAIL ❌"
    summary = {"Correct":correct,"Wrong":wrong,"Blank":blank,"Half Rejected":half_rejected,"All Filled":full_covered,"Score":round(score,2),"Total":total_marks,"Percentage":round(perc,1),"Status":status}
    return summary, results, annotated

# ---------- STEP 3 - CHECK ----------
st.subheader("3⃣ Upload Photos - Result Auto")
if not answer_key:
    st.warning("👆 First give Key, then upload photos.")
    uploaded = st.file_uploader("OMR Photos", type=["jpg","jpeg","png"], accept_multiple_files=True, disabled=True)
else:
    uploaded = st.file_uploader(f"Upload Photos - Key: {','.join(answer_key)}", type=["jpg","jpeg","png"], accept_multiple_files=True)
    if uploaded:
        st.success(f"✅ {len(uploaded)} files - Checking Auto...")
        all_rows=[]
        for f in uploaded:
            st.markdown(f"---\n### 📄 {f.name}")
            pil_img = Image.open(f)
            col1,col2 = st.columns(2)
            with col1: st.image(pil_img, caption="Original", use_container_width=True)
            summary, results, annotated = check_accurate(pil_img, answer_key, total_q, options_per_q, top_cut, bottom_cut, left_cut, right_cut, blank_handle, fill_threshold, half_handle)
            with col2: st.image(annotated, caption="Checked", use_container_width=True)
            a,b,c,d,e,f1,g = st.columns(7)
            a.metric("✅ Correct", summary["Correct"])
            b.metric("❌ Wrong", summary["Wrong"])
            c.metric("⚪ Blank", summary["Blank"])
            g.metric("🌓 Half Rejected", summary["Half Rejected"])
            f1.metric("⬛ All Filled", summary["All Filled"])
            d.metric("🏆 Score", f"{summary['Score']} / {summary['Total']} ({summary['Percentage']}%)")
            e.metric("Pass / Fail", summary["Status"])
            st.info(f"Blank: **{blank_mode}** | Half: **{half_mode}** | Total: **{total_q} (Auto)**")
            st.table(results)
            roll = f.name.rsplit(".",1)[0]
            all_rows.append({"Roll No":roll,"File":f.name, **summary})
        if all_rows:
            st.subheader("📊 Final Result - Auto")
            st.table(all_rows)
            out=io.StringIO()
            w=csv.DictWriter(out, fieldnames=list(all_rows[0].keys()))
            w.writeheader(); w.writerows(all_rows)
            st.download_button("⬇ Download Result CSV", out.getvalue().encode('utf-8'), "result.csv", "text/csv", type="primary")
    else:
        st.info("👆 Upload photos - result will make auto.")
st.caption("OMR Paper Checker | Smart Key | Half Fill Option | All Filled Ignore | No CV2")

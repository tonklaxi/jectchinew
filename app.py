from flask import Flask, request, render_template, send_from_directory, redirect, url_for, session
import cv2
import numpy as np
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

# Folders
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ALLOWED_EXTS = {"png", "jpg", "jpeg"}

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS

def read_roi_rgb(image_path: str):
    """Read image and return mean RGB from center ROI (square ~30% of min dimension)."""
    img = cv2.imread(image_path)  # BGR
    if img is None:
        raise ValueError("ไม่สามารถอ่านไฟล์ภาพได้")
    h, w = img.shape[:2]
    side = int(min(h, w) * 0.3)
    cy, cx = h // 2, w // 2
    y1, y2 = max(0, cy - side // 2), min(h, cy + side // 2)
    x1, x2 = max(0, cx - side // 2), min(w, cx + side // 2)
    roi = img[y1:y2, x1:x2]
    b, g, r = [float(np.mean(roi[:, :, i])) for i in range(3)]
    return (r, g, b), (x1, y1, x2, y2)

def describe_color(rgb):
    r, g, b = rgb
    # Simple descriptive buckets for urine test colors
    if r > g + 30 and r > b + 30:
        desc = "โทนส้ม/เหลืองเข้ม"
    elif g >= r - 10 and g > b + 10:
        desc = "โทนเขียวอ่อน/เหลืองอมเขียว"
    elif r > 200 and g > 200 and b > 200:
        desc = "เกือบขาว"
    else:
        desc = "โทนเหลืองทั่วไป"
    return f"สี: {desc}"

def analyze_value(image_path: str, mode: str):
    """Very lightweight heuristic just for prototype demo.
       - Nitrite: estimate from G channel (0–3 mg/mL)
       - Protein: estimate from R channel (0–300 mg/dL)
    """
    (r, g, b), _ = read_roi_rgb(image_path)
    if not mode:
        return "ไม่ได้ระบุโหมดการทดสอบ", None

    if "nitrite" in mode:
        # darker green (lower G) -> higher nitrite
        nitrite = round((255 - g) / 255 * 3.0, 2)  # mg/mL (dummy scale)
        return f"ปริมาณไนไตรต์: {nitrite} mg/mL", nitrite
    else:
        # protein from R channel (dummy mapping to mg/dL 0–300)
        protein = round(r / 255 * 300, 0)
        return f"ปริมาณโปรตีน: {int(protein)} mg/dL", protein

@app.route('/')
def home():
    return render_template('landing.html')

@app.route('/select-analysis-type')
def select_analysis_type():
    return render_template('select-analysis-type.html')

@app.route('/select-nitrite-mode')
def select_nitrite_mode():
    return render_template('select-nitrite-mode.html')

@app.route('/select-protein-mode')
def select_protein_mode():
    return render_template('select-protein-mode.html')

@app.route('/upload-page')
def upload_page():
    mode = request.args.get('mode')
    if mode:
        session['mode'] = mode
    return render_template('upload.html')

@app.route('/upload', methods=['POST'])
def upload():
    # mode from hidden field or session
    mode = request.form.get('mode') or session.get('mode', '')
    file = request.files.get('file')
    if not file or file.filename == '':
        return "ไม่พบไฟล์อัปโหลด", 400
    if not allowed_file(file.filename):
        return "ไฟล์ไม่รองรับ (รองรับ .png, .jpg, .jpeg)", 400

    filename = secure_filename(f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{file.filename}")
    path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(path)

    try:
        rgb, _ = read_roi_rgb(path)
        urine_result = describe_color(rgb)
        value_result, numeric = analyze_value(path, mode)
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการวิเคราะห์: {e}", 500

    rgb_rounded = tuple(round(c, 2) for c in rgb)
    return render_template('result.html',
                           image_url=url_for('uploaded_file', filename=filename),
                           urine_result=urine_result,
                           value_result=value_result,
                           rgb=rgb_rounded)

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=18800, debug=True)

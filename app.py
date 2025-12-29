from flask import Flask, request, render_template, send_from_directory, url_for, session
import cv2
import numpy as np
import os
from werkzeug.utils import secure_filename
from datetime import datetime

app = Flask(__name__)
app.secret_key = "supersecretkey"

# โฟลเดอร์อัปโหลด (ใช้ path แบบ absolute กันพลาดเวลา deploy)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED_EXTS = {"png", "jpg", "jpeg"}


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTS


def analyze_urine_color(image_path):
    """วิเคราะห์โทนสีแบบ heuristic จาก ROI กึ่งกลาง (คล้ายโค้ดเดิมของคุณ)"""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("ไม่สามารถเปิดไฟล์รูปภาพได้")

    h, w, _ = img.shape
    crop_size = 150
    x1, y1 = max(w // 2 - crop_size // 2, 0), max(h // 2 - crop_size // 2, 0)
    x2, y2 = x1 + crop_size, y1 + crop_size
    roi = img[y1:y2, x1:x2]
    roi = cv2.resize(roi, (200, 200))

    b, g, r = cv2.mean(roi)[:3]
    rgb = (r, g, b)

    if r > 200 and g > 200 and b > 200:
        result = "ใส (อาจดื่มน้ำมาก)"
    elif r > 200 and 150 < g < 200 and b < 100:
        result = "เหลืองอ่อน (ปกติ)"
    elif r > 180 and 100 < g <= 150 and b < 80:
        result = "เหลืองเข้ม (อาจขาดน้ำ)"
    elif r > 150 and 50 < g <= 100 and b < 60:
        result = "ส้ม (ขาดน้ำมาก)"
    elif r > 100 and g < 70 and b < 50:
        result = "น้ำตาล (ควรพบแพทย์)"
    else:
        result = "ไม่สามารถประเมินได้"

    return result, rgb


def analyze_value(image_path, mode: str):
    """คำนวณค่าตามโหมด (สูตรเดียวกับโค้ดเดิม แยก 4 โหมด)"""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError("ไม่สามารถเปิดไฟล์รูปภาพได้")

    img = cv2.resize(img, (200, 200))
    h, w, _ = img.shape
    x1, y1 = w // 2 - 40, h // 2 - 40
    x2, y2 = w // 2 + 40, h // 2 + 40
    roi = img[y1:y2, x1:x2]
    _, g, _ = cv2.mean(roi)[:3]

    if mode == "yellow_protein":
        PCON = g - 208.41
        CON = abs(PCON / 13.433)
        result = f"ปริมาณโปรตีน (Yellow): {CON:.2f} mg/mL"
    elif mode == "white_protein":
        PCON = g - 250.24
        CON = abs(PCON / 35.894)
        result = f"ปริมาณโปรตีน (White): {CON:.2f} mg/mL"
    elif mode == "yellow_nitrite":
        PCON = g - 116.6
        CON = abs(PCON / 75.702)
        result = f"ปริมาณไนไตรต์ (Yellow): {CON:.2f} mg/L"
    elif mode == "white_nitrite":
        PCON = g - 116.6
        CON = abs(PCON / 75.407)
        result = f"ปริมาณไนไตรต์ (White): {CON:.2f} mg/L"
    else:
        return "โหมดไม่ถูกต้อง", 0

    # ปรับ offset เล็กน้อยตามเดิม และไม่ให้ติดลบ
    CON = max(CON - 0.1, 0)
    return result, CON


# -------- Routes --------
@app.route('/')
def landing():
    return render_template("landing.html")

@app.route('/select-analysis-type')
def select_analysis_type():
    return render_template("select-analysis-type.html")

@app.route('/select-protein-mode')
def select_protein_mode():
    return render_template("select-protein-mode.html")

@app.route('/select-nitrite-mode')
def select_nitrite_mode():
    return render_template("select-nitrite-mode.html")

@app.route('/upload-page')
def upload_page():
    mode = request.args.get("mode")
    if mode:
        session['mode'] = mode
    return render_template("upload.html", mode=mode)

@app.route('/upload', methods=['POST'])
def upload():
    # รองรับทั้งชื่อ field แบบใหม่ 'file' และของเดิม 'image'
    file = request.files.get('file') or request.files.get('image')
    if not file or file.filename == '':
        return "ไม่ได้เลือกรูปภาพ", 400
    if not allowed_file(file.filename):
        return "ไฟล์ไม่รองรับ (รองรับ .png, .jpg, .jpeg)", 400

    filename = datetime.now().strftime('%Y%m%d_%H%M%S_') + secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)

    mode = session.get("mode", "yellow_protein")

    try:
        urine_result, rgb = analyze_urine_color(filepath)
        value_result, value_number = analyze_value(filepath, mode)
    except Exception as e:
        return f"เกิดข้อผิดพลาดในการวิเคราะห์: {e}", 500

    rgb_rounded = tuple(round(c, 2) for c in rgb)

    return render_template(
        'result.html',
        image_url=url_for('uploaded_file', filename=filename),
        urine_result=urine_result,
        value_result=value_result,
        rgb=rgb_rounded
    )

@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=18800, debug=True)

import os
import io
import json
import shutil
import tempfile
import asyncio
from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import FastAPI, File, UploadFile, Form, HTTPException, status
from fastapi.responses import HTMLResponse, JSONResponse
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2 import service_account

app = FastAPI(title="科學實驗影音上傳系統")

# 全域排隊鎖：確保向 Google Drive 傳輸時一次只處理一件，防止記憶體與連線過載
upload_lock = asyncio.Lock()

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

# --- Google API 驗證與操作函數 ---
def get_gcp_credentials():
    sa_json = os.environ.get("GCP_SERVICE_ACCOUNT")
    if not sa_json:
        return None
    try:
        creds_dict = json.loads(sa_json)
        return service_account.Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    except Exception as e:
        print(f"GCP 憑證解析失敗: {e}")
        return None

def sync_drive_upload(creds, file_path: str, file_name: str, folder_id: str, mime_type: str) -> str:
    """從硬碟路徑串流上傳至 Google Drive，不載入 RAM"""
    service = build('drive', 'v3', credentials=creds, cache_discovery=False)
    file_metadata = {
        'name': file_name,
        'parents': [folder_id]
    }
    media = MediaFileUpload(
        file_path,
        mimetype=mime_type or "application/octet-stream",
        chunksize=5 * 1024 * 1024,
        resumable=True
    )
    request = service.files().create(
        body=file_metadata,
        media_body=media,
        fields='id',
        supportsAllDrives=True
    )
    response = None
    while response is None:
        status_code, response = request.next_chunk()
    return response.get('id')

def sync_sheet_append(creds, sheet_id: str, row_data: list) -> bool:
    """寫入試算表 A:F 欄位"""
    service = build('sheets', 'v4', credentials=creds, cache_discovery=False)
    body = {'values': [row_data]}
    service.spreadsheets().values().append(
        spreadsheetId=sheet_id,
        range="A:F",
        valueInputOption="USER_ENTERED",
        body=body
    ).execute()
    return True

# --- API 端點 ---

@app.post("/api/verify-password")
async def verify_password(payload: dict):
    correct_password = os.environ.get("APP_PASSWORD", "science")
    if payload.get("password") == correct_password:
        return {"success": True}
    return JSONResponse(status_code=401, content={"success": False, "message": "密碼錯誤"})

@app.post("/api/upload")
async def handle_upload(
    password: str = Form(...),
    grade: str = Form(...),
    room: str = Form(...),
    seats: str = Form(...),  # 格式如："1,7,13"
    topic: str = Form(...),
    result_text: str = Form(...),
    file: UploadFile = File(...)
):
    correct_password = os.environ.get("APP_PASSWORD", "science")
    if password != correct_password:
        raise HTTPException(status_code=401, detail="密碼驗證失敗")

    drive_folder_id = os.environ.get("DRIVE_FOLDER_ID")
    spreadsheet_id = os.environ.get("SPREADSHEET_ID")
    creds = get_gcp_credentials()

    if not creds or not drive_folder_id or not spreadsheet_id:
        raise HTTPException(status_code=500, detail="伺服器環境變數未配置完整")

    # 1. 解析座號格式
    try:
        seat_list = [int(s.strip()) for s in seats.split(",") if s.strip()]
        seat_list = sorted(list(set(seat_list)))[:4]
        if not seat_list:
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=400, detail="座號格式不正確")

    seats_dot_str = ".".join([f"{s:02d}" for s in seat_list])
    seats_compact_str = "".join([f"{s:02d}" for s in seat_list])

    # 2. 班級與時間格式化
    grade_num = grade.replace("年級", "").strip()
    room_num = room.replace("班", "").strip().zfill(2)
    class_str = f"{grade_num}{room_num}"

    tw_tz = timezone(timedelta(hours=8))
    now = datetime.now(tw_tz)
    upload_time = now.strftime("%Y-%m-%d %H:%M:%S")
    file_time_str = now.strftime("%Y%m%d_%H%M%S")

    ext = file.filename.split('.')[-1] if '.' in file.filename else "mp4"
    final_name = f"{file_time_str}_{class_str}_{seats_compact_str}_{topic[:10]}_{result_text[:20]}.{ext}"

    # 3. 分塊儲存至磁碟暫存檔（控制 RAM 消耗在 1MB 以內）
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = tmp.name
        shutil.copyfileobj(file.file, tmp)

    # 4. 進入排隊鎖，依序推送到雲端
    try:
        async with upload_lock:
            # 串流至 Google Drive
            file_id = await asyncio.to_thread(
                sync_drive_upload,
                creds, tmp_path, final_name, drive_folder_id, file.content_type
            )
            if not file_id:
                raise HTTPException(status_code=500, detail="Google Drive 上傳失敗")

            # 寫入 Google Sheets (欄位對齊 A:F)
            row_data = [
                upload_time,
                class_str,
                seats_dot_str,
                topic[:10],
                result_text[:20],
                final_name
            ]
            await asyncio.to_thread(sync_sheet_append, creds, spreadsheet_id, row_data)

        return {"success": True, "filename": final_name}

    finally:
        # 強制清理磁碟空間
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

# --- 前端網頁介面 (針對平板觸控最佳化) ---
@app.get("/", response_class=HTMLResponse)
async def serve_ui():
    return """
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>科學實驗影音上傳系統</title>
  <style>
    :root {
      --primary: #2563eb;
      --primary-hover: #1d4ed8;
      --bg: #f8fafc;
      --card-bg: #ffffff;
      --text: #1e293b;
      --border: #cbd5e1;
    }
    * { box-sizing: border-box; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); margin: 0; padding: 16px; display: flex; justify-content: center; }
    .card { background: var(--card-bg); width: 100%; max-width: 580px; padding: 24px; border-radius: 12px; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1); }
    h1 { font-size: 1.4rem; text-align: center; margin-bottom: 20px; }
    .hidden { display: none !important; }
    .form-group { margin-bottom: 16px; }
    label { display: block; font-weight: 600; margin-bottom: 6px; font-size: 0.95rem; }
    input[type="text"], input[type="password"], input[type="file"] {
      width: 100%; padding: 10px; border: 1px solid var(--border); border-radius: 8px; font-size: 1rem;
    }
    .radio-group { display: flex; gap: 8px; flex-wrap: wrap; }
    .radio-pill {
      flex: 1; text-align: center; padding: 8px 12px; border: 1px solid var(--border); border-radius: 8px;
      cursor: pointer; user-select: none; font-size: 0.95rem; background: #fff;
    }
    .radio-pill.selected { background: var(--primary); color: #fff; border-color: var(--primary); font-weight: bold; }
    .seat-grid { display: grid; grid-template-columns: repeat(6, 1fr); gap: 6px; }
    .seat-btn {
      padding: 10px 0; border: 1px solid var(--border); background: #f1f5f9; border-radius: 6px;
      cursor: pointer; font-size: 0.95rem; font-weight: 600; text-align: center; user-select: none;
    }
    .seat-btn.selected { background: var(--primary); color: #fff; border-color: var(--primary); }
    button.submit-btn {
      width: 100%; padding: 12px; background: var(--primary); color: #fff; border: none;
      border-radius: 8px; font-size: 1.1rem; font-weight: bold; cursor: pointer; margin-top: 10px;
    }
    button.submit-btn:disabled { background: #94a3b8; cursor: not-allowed; }
    .alert { padding: 10px; border-radius: 6px; margin-bottom: 12px; font-size: 0.9rem; }
    .alert-error { background: #fee2e2; color: #991b1b; }
    .alert-success { background: #dcfce7; color: #166534; }
    .loading-overlay {
      position: fixed; top: 0; left: 0; width: 100%; height: 100%;
      background: rgba(255,255,255,0.9); display: flex; flex-direction: column;
      align-items: center; justify-content: center; z-index: 1000;
    }
    .spinner {
      border: 4px solid #f3f3f3; border-top: 4px solid var(--primary);
      border-radius: 50%; width: 45px; height: 45px; animation: spin 1s linear infinite; margin-bottom: 12px;
    }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
  </style>
</head>
<body>

<div class="card">
  <h1>🔬 科學實驗影音上傳系統</h1>

  <!-- 密碼解鎖區 -->
  <div id="lock-section">
    <div class="form-group">
      <label>請輸入通關密碼：</label>
      <input type="password" id="app-password" placeholder="請輸入密碼">
    </div>
    <div id="password-error" class="alert alert-error hidden">密碼錯誤。</div>
    <button class="submit-btn" onclick="verifyPassword()">驗證解鎖</button>
  </div>

  <!-- 上傳介面區 -->
  <div id="upload-section" class="hidden">
    <div id="status-box"></div>

    <div class="form-group">
      <label>選擇年級：</label>
      <div class="radio-group" id="grade-group">
        <div class="radio-pill" onclick="selectPill('grade', this, '3年級')">3年級</div>
        <div class="radio-pill" onclick="selectPill('grade', this, '4年級')">4年級</div>
        <div class="radio-pill selected" onclick="selectPill('grade', this, '5年級')">5年級</div>
        <div class="radio-pill" onclick="selectPill('grade', this, '6年級')">6年級</div>
      </div>
    </div>

    <div class="form-group">
      <label>選擇班級：</label>
      <div class="radio-group" id="room-group">
        <div class="radio-pill selected" onclick="selectPill('room', this, '1班')">1班</div>
        <div class="radio-pill" onclick="selectPill('room', this, '2班')">2班</div>
        <div class="radio-pill" onclick="selectPill('room', this, '3班')">3班</div>
        <div class="radio-pill" onclick="selectPill('room', this, '4班')">4班</div>
        <div class="radio-pill" onclick="selectPill('room', this, '5班')">5班</div>
      </div>
    </div>

    <div class="form-group">
      <label>選擇座號（點擊選取，最多 4 位）：</label>
      <div class="seat-grid" id="seat-grid"></div>
    </div>

    <div class="form-group">
      <label>實驗主題（限 10 字）：</label>
      <input type="text" id="topic" maxlength="10" placeholder="例如：雲霧實驗">
    </div>

    <div class="form-group">
      <label>實驗成果（限 20 字）：</label>
      <input type="text" id="result-text" maxlength="20" placeholder="例如：有線香霧氣比較明顯">
    </div>

    <div class="form-group">
      <label>上傳檔案（支援照片與影片，上限 100MB）：</label>
      <input type="file" id="file-input" accept="video/*,image/*,.heic,.mov,.mp4,.avi,.jpg,.png">
    </div>

    <button class="submit-btn" id="upload-btn" onclick="startUpload()">🚀 開始上傳到雲端</button>
  </div>
</div>

<div id="loading" class="loading-overlay hidden">
  <div class="spinner"></div>
  <h3 style="margin:0;">正在排隊與上傳雲端...</h3>
  <p style="color:#64748b; margin-top:8px;">請勿關閉視窗或重新整理頁面</p>
</div>

<script>
  let authenticatedPassword = "";
  let selectedGrade = "5年級";
  let selectedRoom = "1班";
  let selectedSeats = [];

  // 生成 1~34 號座號按鈕
  const seatGrid = document.getElementById("seat-grid");
  for (let i = 1; i <= 34; i++) {
    const btn = document.createElement("div");
    btn.className = "seat-btn";
    btn.textContent = String(i).padStart(2, '0') + "號";
    btn.onclick = () => toggleSeat(i, btn);
    seatGrid.appendChild(btn);
  }

  function toggleSeat(seatNum, element) {
    if (selectedSeats.includes(seatNum)) {
      selectedSeats = selectedSeats.filter(s => s !== seatNum);
      element.classList.remove("selected");
    } else {
      if (selectedSeats.length >= 4) {
        alert("最多只能選擇 4 位組員座號！");
        return;
      }
      selectedSeats.push(seatNum);
      element.classList.add("selected");
    }
  }

  function selectPill(type, element, value) {
    const parent = element.parentElement;
    parent.querySelectorAll(".radio-pill").forEach(p => p.classList.remove("selected"));
    element.classList.add("selected");
    if (type === 'grade') selectedGrade = value;
    if (type === 'room') selectedRoom = value;
  }

  async function verifyPassword() {
    const pwd = document.getElementById("app-password").value;
    const res = await fetch("/api/verify-password", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: pwd })
    });
    if (res.ok) {
      authenticatedPassword = pwd;
      document.getElementById("lock-section").classList.add("hidden");
      document.getElementById("upload-section").classList.remove("hidden");
    } else {
      document.getElementById("password-error").classList.remove("hidden");
    }
  }

  async function startUpload() {
    const topic = document.getElementById("topic").value.trim();
    const resultText = document.getElementById("result-text").value.trim();
    const fileInput = document.getElementById("file-input");
    const file = fileInput.files[0];

    if (!selectedSeats.length || !topic || !resultText || !file) {
      alert("⚠️ 請確認座號、主題、成果及檔案皆已完整填寫！");
      return;
    }

    if (file.size > 104857600) { // 100MB
      alert("⚠️ 檔案超過 100MB 限制，請壓縮後再行上傳！");
      return;
    }

    const formData = new FormData();
    formData.append("password", authenticatedPassword);
    formData.append("grade", selectedGrade);
    formData.append("room", selectedRoom);
    formData.append("seats", selectedSeats.join(","));
    formData.append("topic", topic);
    formData.append("result_text", resultText);
    formData.append("file", file);

    const loading = document.getElementById("loading");
    loading.classList.remove("hidden");

    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        body: formData
      });
      const data = await res.json();
      if (res.ok && data.success) {
        alert("✅ 上傳與記錄成功！\\n檔案名稱：" + data.filename);
        // 清空表單
        document.getElementById("topic").value = "";
        document.getElementById("result-text").value = "";
        fileInput.value = "";
        selectedSeats = [];
        document.querySelectorAll(".seat-btn").forEach(b => b.classList.remove("selected"));
      } else {
        alert("❌ 上傳失敗：" + (data.detail || "伺服器發生錯誤"));
      }
    } catch (e) {
      alert("❌ 連線異常或處理逾時，請稍候重試。");
    } finally {
      loading.classList.add("hidden");
    }
  }
</script>
</body>
</html>
    """

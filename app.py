import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from google.oauth2 import service_account
import io

# 1. 網頁基本設定
st.set_page_config(page_title="科學實驗影片上傳", page_icon="🔬", layout="centered")
st.title("🔬 科學實驗影片上傳系統")

# 2. 安全密碼鎖 (透過 secrets 保護)
correct_password = st.secrets.get("app_password", "science")
password = st.text_input("請輸入通關密碼以解鎖上傳區：", type="password")

# --- Google Drive 上傳函數 ---
def upload_to_drive(file_obj, file_name):
    try:
        # 從 Secrets 讀取 Google 服務帳戶資訊
        creds_dict = st.secrets["gcp_service_account"]
        creds = service_account.Credentials.from_service_account_info(creds_dict)
        service = build('drive', 'v3', credentials=creds)

        # 設定檔案元數據 (Metadata)
        file_metadata = {
            'name': file_name,
            'parents': [st.secrets["drive_folder_id"]] # 雲端硬碟資料夾 ID
        }
        
        # 準備檔案內容
        media = MediaIoBaseUpload(io.BytesIO(file_obj.read()), mimetype=file_obj.type, resumable=True)
        
        # 執行上傳
        file = service.files().create(body=file_metadata, media_body=media, fields='id',supportsAllDrives=True).execute()
        return file.get('id')
    except Exception as e:
        st.error(f"上傳發生錯誤：{e}")
        return None

if password == correct_password:
    # --- 欄位設計 (與之前相同) ---
    grade = st.radio("選擇年級：", ["3年級", "4年級", "5年級", "6年級"], horizontal=True)
    room = st.radio("選擇班級：", ["1班", "2班", "3班", "4班", "5班"], horizontal=True)
    
    st.divider()
    st.write("選擇座號（最多 4 位）：")
    if 'selected_seats' not in st.session_state: st.session_state.selected_seats = []
    
    cols = st.columns(6)
    for i in range(1, 35):
        is_selected = i in st.session_state.selected_seats
        if cols[(i-1)%6].button(f"{i:02d}號", key=f"s{i}", type="primary" if is_selected else "secondary", use_container_width=True):
            if is_selected: st.session_state.selected_seats.remove(i)
            elif len(st.session_state.selected_seats) < 4: st.session_state.selected_seats.append(i)
            st.rerun()
            
    if st.session_state.selected_seats:
        sorted_seats = sorted(st.session_state.selected_seats)
        st.info(f"👉 已選座號：**{'、'.join([f'{s:02d}號' for s in sorted_seats])}**")

    topic = st.text_input("實驗主題：")
    uploaded_file = st.file_uploader("上傳實驗影片檔", type=["mp4", "mov", "avi"])

    # --- 確認上傳按鈕 ---
    if st.button("🚀 開始上傳到雲端", type="primary"):
        if not st.session_state.selected_seats or not topic or not uploaded_file:
            st.warning("⚠️ 請檢查座號、主題與檔案是否都填好了？")
        else:
            with st.spinner("影片正在上傳中，請勿關閉視窗..."):
                seats_str = "_".join([f"{s:02d}" for s in sorted(st.session_state.selected_seats)])
                # 根據您的需求自動命名
                final_name = f"{grade}_{room}_{seats_str}號_{topic}.mp4"
                
                file_id = upload_to_drive(uploaded_file, final_name)
                
                if file_id:
                    st.success(f"✅ 上傳成功！檔名為：{final_name}")
                    st.balloons()
                    # 上傳成功後清空選擇，方便下一位學生
                    st.session_state.selected_seats = []

elif password != "":
    st.error("密碼錯誤。")

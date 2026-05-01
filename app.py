import streamlit as st

# 1. 網頁基本設定
st.set_page_config(page_title="科學實驗影片上傳", page_icon="🔬", layout="centered")
st.title("🔬 科學實驗影片上傳系統")

# 2. 簡單密碼鎖
password = st.text_input("請輸入通關密碼以解鎖上傳區：", type="password")

# 這裡先設定一個簡單的密碼 "science" 測試用
if password == "science":
    st.success("密碼正確！請填寫以下上傳資訊：")
    
    st.divider() # 分隔線
    
    # --- 欄位 1：年級 (3-6) ---
    # horizontal=True可以讓選項橫向排列，變成類似方格點選的效果
    grade = st.radio("選擇年級：", ["3年級", "4年級", "5年級", "6年級"], horizontal=True)
    
    # --- 欄位 2：班級 (1-5) ---
    room = st.radio("選擇班級：", ["1班", "2班", "3班", "4班", "5班"], horizontal=True)
    
    st.divider()
    
    # --- 欄位 3：座號 (1-34) ---
    st.write("選擇座號：")
    
    # 使用 session_state 來記住使用者按下的座號
    if 'seat_number' not in st.session_state:
        st.session_state.seat_number = None
        
    # 建立 6 個直行來排版座號按鈕 (形成數字網格)
    cols = st.columns(6)
    for i in range(1, 35):
        col_idx = (i - 1) % 6
        with cols[col_idx]:
            # 當按鈕被按下時，把數字存入 session_state
            if st.button(f"{i:02d}號", key=f"seat_{i}", use_container_width=True):
                st.session_state.seat_number = i
                
    # 顯示目前選到的座號，讓使用者確認
    if st.session_state.seat_number is not None:
        st.info(f"👉 目前選擇的座號：**{st.session_state.seat_number:02d}號**")

    st.divider()

    # --- 欄位 4：實驗主題 ---
    topic = st.text_input("實驗主題（例如：光合作用觀察、燃燒的條件等）：")
    
    # --- 欄位 5：上傳檔案 ---
    uploaded_file = st.file_uploader("上傳實驗影片檔", type=["mp4", "mov", "avi"])
    
    # --- 確認按鈕與防呆機制 ---
    if st.button("確認上傳", type="primary"):
        if st.session_state.seat_number is None:
            st.error("⚠️ 請記得在上方點選座號！")
        elif not topic:
            st.error("⚠️ 請填寫實驗主題！")
        elif not uploaded_file:
            st.error("⚠️ 請上傳影片檔案！")
        else:
            # 這裡我們先把未來要傳給 Google Drive 的檔名組合起來測試
            file_name = f"{grade}_{room}_{st.session_state.seat_number:02d}號_{topic}.mp4"
            st.success(f"✅ 資料確認無誤！\n\n未來在 Google Drive 自動命名的檔名將會是：**{file_name}**")
            st.write("（下一步我們就會將 Google Drive API 的上傳功能寫進這裡）")

elif password != "":
    st.error("密碼錯誤，請重新輸入。")
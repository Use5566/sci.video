import streamlit as st

# 1. 網頁基本設定
st.set_page_config(page_title="科學實驗影片上傳", page_icon="🔬", layout="centered")
st.title("🔬 科學實驗影片上傳系統")

# 2. 安全密碼鎖 (透過 secrets 保護)
# 使用 st.secrets.get() 可以避免本機還沒設定時直接當機。
# 正式上線前，請在 Streamlit Cloud 後台設定 app_password = "您的真實密碼"
correct_password = st.secrets.get("app_password", "science")

password = st.text_input("請輸入通關密碼以解鎖上傳區：", type="password")

if password == correct_password:
    st.success("密碼正確！請填寫以下上傳資訊：")
    st.divider() 
    
    # --- 欄位 1：年級 (3-6) ---
    grade = st.radio("選擇年級：", ["3年級", "4年級", "5年級", "6年級"], horizontal=True)
    
    # --- 欄位 2：班級 (1-5) ---
    room = st.radio("選擇班級：", ["1班", "2班", "3班", "4班", "5班"], horizontal=True)
    
    st.divider()
    
    # --- 欄位 3：座號 (1-34，最多複選 4 位) ---
    st.write("選擇座號（小組成員，最多可選 4 位）：")
    
    # 使用 session_state 儲存一個「清單」來記錄已選擇的座號
    if 'selected_seats' not in st.session_state:
        st.session_state.selected_seats = []
        
    cols = st.columns(6)
    for i in range(1, 35):
        col_idx = (i - 1) % 6
        # 檢查該座號是否已經被選取
        is_selected = i in st.session_state.selected_seats
        
        # 如果被選中，按鈕顏色變深 (primary)，否則為淺色 (secondary)
        btn_type = "primary" if is_selected else "secondary"
        
        with cols[col_idx]:
            # 按鈕被按下時的觸發邏輯
            if st.button(f"{i:02d}號", key=f"seat_{i}", type=btn_type, use_container_width=True):
                if is_selected:
                    # 如果已經選了，再次點擊就是取消選擇
                    st.session_state.selected_seats.remove(i)
                    st.rerun() # 重新整理頁面以更新按鈕顏色
                else:
                    # 如果還沒選，檢查是否已經選滿 4 人
                    if len(st.session_state.selected_seats) < 4:
                        st.session_state.selected_seats.append(i)
                        st.rerun()
                    else:
                        st.error("⚠️ 最多只能選擇 4 位座號喔！")
                        
    # 顯示目前選到的座號，將數字排序並格式化
    if st.session_state.selected_seats:
        sorted_seats = sorted(st.session_state.selected_seats)
        seats_str = "、".join([f"{s:02d}號" for s in sorted_seats])
        st.info(f"👉 目前已選擇的座號：**{seats_str}**")
    else:
        st.info("👉 尚未選擇座號")

    st.divider()

    # --- 欄位 4：實驗主題 ---
    topic = st.text_input("實驗主題：")
    
    # --- 欄位 5：上傳檔案 ---
    uploaded_file = st.file_uploader("上傳實驗影片檔", type=["mp4", "mov", "avi"])
    
    # --- 確認按鈕與防呆機制 ---
    if st.button("確認上傳", type="primary"):
        if len(st.session_state.selected_seats) == 0:
            st.error("⚠️ 請至少選擇一位座號！")
        elif not topic:
            st.error("⚠️ 請填寫實驗主題！")
        elif not uploaded_file:
            st.error("⚠️ 請上傳影片檔案！")
        else:
            # 組合檔名：把多個座號串起來 (例如：01_05_12)
            seats_for_filename = "_".join([f"{s:02d}" for s in sorted(st.session_state.selected_seats)])
            file_name = f"{grade}_{room}_{seats_for_filename}號_{topic}.mp4"
            st.success(f"✅ 資料確認無誤！\n\n未來在 Google Drive 的自動命名將會是：\n**{file_name}**")

elif password != "":
    st.error("密碼錯誤，請重新輸入。")

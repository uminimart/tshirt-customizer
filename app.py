import os
import io
import streamlit as st
from PIL import Image
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

SCOPES = ['https://www.googleapis.com/auth/drive.readonly', 'https://www.googleapis.com/auth/drive.file']

st.set_page_config(page_title="T-Shirt Studio - E-commerce", layout="wide")

TARGET_FOLDER_ID = ""

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button {
        background-color: #D70F64;
        color: white;
        border-radius: 10px;
        border: none;
        font-weight: bold;
        padding: 8px;
    }
    .stButton>button:hover {
        background-color: #b00c50;
        color: white;
    }
    .shop-card {
        background-color: white;
        padding: 12px;
        border-radius: 12px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.06);
        margin-bottom: 10px;
    }
    .selected-border { border: 3px solid #D70F64 !important; border-radius: 10px; padding: 2px; }
    .unselected-border { border: 1px solid #ddd; border-radius: 10px; padding: 2px; }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists('credentials.json'):
                return None
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

@st.cache_data(ttl=86400, show_spinner=False)
def download_image(file_id):
    service = get_drive_service()
    if not service:
        return None
    try:
        request = service.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request, chunksize=2048*2048)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return Image.open(fh).convert("RGBA")
    except Exception as e:
        return None

def find_file_id_by_name(filename):
    service = get_drive_service()
    if not service:
        return None
    try:
        query = f"name = '{filename}' and trashed = false"
        res = service.files().list(q=query, fields="files(id, name)").execute()
        files = res.get('files', [])
        if files:
            return files[0]['id']
    except Exception as e:
        pass
    return None

def upload_file_to_drive(file_bytes, filename, mime_type):
    service = get_drive_service()
    if not service:
        return None
    try:
        temp_path = f"temp_{filename}"
        with open(temp_path, "wb") as f:
            f.write(file_bytes)
        
        file_metadata = {'name': filename}
        if TARGET_FOLDER_ID and TARGET_FOLDER_ID.strip() != "":
            file_metadata['parents'] = [TARGET_FOLDER_ID]
            
        media = MediaFileUpload(temp_path, mimetype=mime_type)
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        if os.path.exists(temp_path):
            os.remove(temp_path)
        return file.get('id')
    except Exception as e:
        return None

@st.cache_data(ttl=3600, show_spinner=False)
def load_folder_items(folder_name):
    service = get_drive_service()
    if not service:
        return {}
    try:
        query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{folder_name}' and trashed = false"
        res = service.files().list(q=query, fields="files(id, name)").execute()
        folders = res.get('files', [])
        if not folders:
            return {}
        
        folder_id = folders[0]['id']
        fq = f"'{folder_id}' in parents and (mimeType = 'image/png' or mimeType = 'image/jpeg') and trashed = false"
        files = service.files().list(q=fq, pageSize=50, fields="files(id, name)").execute().get('files', [])
        
        items_dict = {}
        for file in files:
            name_no_ext = os.path.splitext(file['name'])[0]
            items_dict[name_no_ext] = {'id': file['id'], 'filename': name_no_ext}
        return items_dict
    except Exception as e:
        return {}

@st.cache_data(ttl=3600, show_spinner=False)
def load_sticker_categories():
    service = get_drive_service()
    if not service:
        return {}
    try:
        results = service.files().list(
            q="mimeType = 'application/vnd.google-apps.folder' and name != 'Tee Design' and name != 'Tee Design Back' and trashed = false",
            pageSize=50,
            fields="files(id, name)"
        ).execute()
        folders = results.get('files', [])
        
        categories = {}
        for folder in folders:
            folder_id = folder['id']
            folder_name = folder['name']
            query = f"'{folder_id}' in parents and (mimeType = 'image/png' or mimeType = 'image/jpeg') and trashed = false"
            files = service.files().list(q=query, pageSize=50, fields="files(id, name)").execute().get('files', [])
            if files:
                cleaned_files = []
                for f in files:
                    name_no_ext = os.path.splitext(f['name'])[0]
                    cleaned_files.append({'id': f['id'], 'filename': name_no_ext})
                categories[folder_name] = cleaned_files
        return categories
    except Exception as e:
        return {}

# Session States
if 'selected_tshirt' not in st.session_state:
    st.session_state.selected_tshirt = None
if 'selected_sticker' not in st.session_state:
    st.session_state.selected_sticker = None
if 'cart' not in st.session_state:
    st.session_state.cart = []
if 'checkout_step' not in st.session_state:
    st.session_state.checkout_step = 'customizer'
if 'last_order_info' not in st.session_state:
    st.session_state.last_order_info = None

service = get_drive_service()
if not service:
    st.error("Google Drive API ချိတ်ဆက်ရန် credentials.json ဖိုင် လိုအပ်ပါသည်။")
else:
    front_designs = load_folder_items("Tee Design")
    back_designs = load_folder_items("Tee Design Back")
    sticker_categories = load_sticker_categories()

    if front_designs and not st.session_state.selected_tshirt:
        st.session_state.selected_tshirt = list(front_designs.keys())[0]

    # --- LEFT SIDEBAR: SELECT T-SHIRT (DIRECT TOUCH, NO BUTTON) ---
    st.sidebar.markdown("### 👕 Select T-Shirt")
    if front_designs:
        for key in front_designs.keys():
            is_active = (st.session_state.selected_tshirt == key)
            border_cls = "selected-border" if is_active else "unselected-border"
            
            thumb = download_image(front_designs[key]['id'])
            if thumb:
                st.sidebar.markdown(f"<div class='{border_cls}' style='text-align:center; margin-bottom:8px;'>", unsafe_allow_html=True)
                st.sidebar.image(thumb.resize((100, 120), Image.Resampling.LANCZOS), use_container_width=True)
                st.sidebar.markdown("</div>", unsafe_allow_html=True)
                
                if st.sidebar.button(f"{key}", key=f"sb_t_{key}", use_container_width=True):
                    st.session_state.selected_tshirt = key
                    st.rerun()

    st.sidebar.markdown("---")
    cart_total_items = sum(i['qty'] for i in st.session_state.cart)
    if st.sidebar.button(f"🛒 View Cart ({cart_total_items})", use_container_width=True):
        st.session_state.checkout_step = 'cart'
        st.rerun()

    # --- MAIN CONTAINER ---
    st.markdown("""
        <div style='background-color: #D70F64; padding: 10px; border-radius: 8px; text-align: center; color: white; margin-bottom: 15px;'>
            <h3 style='margin: 0; font-size: 18px;'>🐼 T-Shirt Customizer Studio</h3>
        </div>
    """, unsafe_allow_html=True)

    if st.session_state.checkout_step == 'customizer':
        
        col_main, col_stickers = st.columns([2, 1])

        with col_main:
            st.markdown("#### 👀 Live Preview (Front & Back HD)")
            prev_col1, prev_col2 = st.columns(2)
            
            current_tshirt = st.session_state.selected_tshirt
            current_stk = st.session_state.selected_sticker

            front_id = front_designs.get(current_tshirt, {}).get('id') if current_tshirt in front_designs else None
            back_id = back_designs.get(current_tshirt, {}).get('id') if current_tshirt in back_designs else front_id

            def get_preview_image(f_id, s_info):
                f_img = download_image(f_id)
                if not f_img:
                    return None
                f_copy = f_img.copy().resize((280, 360), Image.Resampling.LANCZOS)
                if s_info:
                    s_img = download_image(s_info['id'])
                    if s_img:
                        s_resized = s_img.copy().resize((100, 100), Image.Resampling.LANCZOS)
                        f_copy.paste(s_resized, (90, 100), s_resized)
                return f_copy

            with prev_col1:
                st.markdown("<div class='shop-card' style='text-align:center;'>", unsafe_allow_html=True)
                st.markdown(f"<b>Front View ({current_tshirt})</b>", unsafe_allow_html=True)
                if front_id:
                    composite_front = get_preview_image(front_id, current_stk)
                    if composite_front:
                        st.image(composite_front, use_container_width=True)
                if current_stk:
                    st.markdown(f"<p style='color:#D70F64; font-size:11px; margin:2px;'>Sticker: {current_stk['category']} / <b>{current_stk['name']}</b></p>", unsafe_allow_html=True)
                st.markdown("</div>", unsafe_allow_html=True)

            with prev_col2:
                st.markdown("<div class='shop-card' style='text-align:center;'>", unsafe_allow_html=True)
                st.markdown(f"<b>Back View ({current_tshirt})</b>", unsafe_allow_html=True)
                if back_id:
                    b_img = download_image(back_id)
                    if b_img:
                        b_copy = b_img.copy().resize((280, 360), Image.Resampling.LANCZOS)
                        st.image(b_copy, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)

            st.markdown("---")
            qty = st.number_input("မှာယူမည့် အရေအတွက် (Quantity)", min_value=1, max_value=50, value=1, step=1)
            
            if st.button("🛒 Add to Cart", use_container_width=True):
                if not current_stk:
                    st.warning("ကျေးဇူးပြု၍ စတစ်ကာ (Sticker) တစ်ခုကို ရွေးချယ်ပါ။")
                else:
                    comp_img = get_preview_image(front_id, current_stk)
                    img_byte_arr = io.BytesIO()
                    if comp_img:
                        comp_img.save(img_byte_arr, format='PNG')
                        snapshot_bytes = img_byte_arr.getvalue()
                    else:
                        snapshot_bytes = None

                    cart_item = {
                        'tshirt': current_tshirt,
                        'front_id': front_id,
                        'back_id': back_id,
                        'sticker_name': current_stk['name'],
                        'sticker_id': current_stk['id'],
                        'sticker_category': current_stk['category'],
                        'snapshot_bytes': snapshot_bytes,
                        'qty': qty,
                        'price': 15000 * qty
                    }
                    st.session_state.cart.append(cart_item)
                    st.success("✅ Add to Cart သို့ အောင်မြင်စွာ ထည့်သွင်းပြီးပါပြီ!")

        # Right Side: Vertical Sticker Scroll Container
        with col_stickers:
            st.markdown("#### 🎨 Select Sticker")
            if sticker_categories:
                cat_names = list(sticker_categories.keys())
                selected_cat = st.selectbox("Category", cat_names)
                
                stickers = sticker_categories[selected_cat]
                
                st.markdown("<div style='max-height: 500px; overflow-y: auto; padding-right: 5px;'>", unsafe_allow_html=True)
                for stk in stickers:
                    stk_thumb = download_image(stk['id'])
                    if stk_thumb:
                        is_active = (current_stk and current_stk['id'] == stk['id'])
                        border_cls = "selected-border" if is_active else "unselected-border"
                        
                        st.markdown(f"<div class='{border_cls}' style='text-align:center; margin-bottom:8px;'>", unsafe_allow_html=True)
                        st.image(stk_thumb.resize((80, 80), Image.Resampling.LANCZOS), use_container_width=True)
                        st.markdown("</div>", unsafe_allow_html=True)
                        
                        if st.button(f"{stk['filename']}", key=f"stk_v_{stk['id']}", use_container_width=True):
                            st.session_state.selected_sticker = {
                                'id': stk['id'],
                                'name': stk['filename'],
                                'category': selected_cat
                            }
                            st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    elif st.session_state.checkout_step == 'cart':
        st.subheader("🛒 Your Shopping Cart")
        
        if st.button("🎨 ဒီဇိုင်းပြန်ဆွဲမည်"):
            st.session_state.checkout_step = 'customizer'
            st.rerun()
            
        st.markdown("---")

        if not st.session_state.cart:
            st.info("Your cart is empty.")
        else:
            grand_total = 0
            items_to_remove = []
            
            for i, item in enumerate(st.session_state.cart):
                st.markdown(f"<div class='shop-card'>", unsafe_allow_html=True)
                st.markdown(f"#### Item #{i+1}")
                
                img_c1, img_c2, img_c3 = st.columns([1, 2, 1])
                with img_c1:
                    if item.get('snapshot_bytes'):
                        st.image(Image.open(io.BytesIO(item['snapshot_bytes'])), use_container_width=True)
                with img_c2:
                    st.write(f"• **T-Shirt:** {item['tshirt']}")
                    st.write(f"• **Sticker:** [{item['sticker_category']}] {item['sticker_name']}")
                    st.write("• **Price per unit:** 15,000 MMK")
                    
                    qty_col1, qty_col2, qty_col3 = st.columns([1, 1, 1])
                    with qty_col1:
                        if st.button("➖", key=f"dec_{i}"):
                            if item['qty'] > 1:
                                item['qty'] -= 1
                                item['price'] = 15000 * item['qty']
                                st.rerun()
                    with qty_col2:
                        st.markdown(f"<h4 style='text-align:center; margin:0;'>{item['qty']}</h4>", unsafe_allow_html=True)
                    with qty_col3:
                        if st.button("➕", key=f"inc_{i}"):
                            item['qty'] += 1
                            item['price'] = 15000 * item['qty']
                            st.rerun()
                            
                    st.write(f"• **Subtotal:** **{item['price']:,} MMK**")

                with img_c3:
                    if st.button("🗑️ Remove", key=f"rem_{i}"):
                        items_to_remove.append(i)

                grand_total += item['price']
                st.markdown("</div>", unsafe_allow_html=True)
            
            if items_to_remove:
                for idx in sorted(items_to_remove, reverse=True):
                    st.session_state.cart.pop(idx)
                st.rerun()

            st.markdown(f"### စုစုပေါင်းကျသင့်ငွေ: <span style='color:#D70F64;'>{grand_total:,} MMK</span>", unsafe_allow_html=True)
            
            col_c1, col_c2 = st.columns(2)
            with col_c1:
                if st.button("💳 ငွေပေးချေမည် (Checkout)", use_container_width=True):
                    st.session_state.checkout_step = 'payment'
                    st.rerun()
            with col_c2:
                if st.button("🗑️ Cart အားလုံးရှင်းမည်", use_container_width=True):
                    st.session_state.cart = []
                    st.rerun()

    elif st.session_state.checkout_step == 'payment':
        st.subheader("💳 MMQR Payment")
        if st.button("⬅️ Cart သို့ ပြန်သွားမည်"):
            st.session_state.checkout_step = 'cart'
            st.rerun()
            
        st.markdown("<div class='shop-card' style='text-align:center;'>", unsafe_allow_html=True)
        st.info("📱 KBZPay / AYA Pay MMQR Code သို့ ငွေလွှဲပါ")
        
        mmqr_id = find_file_id_by_name("mmqr.jpg")
        if mmqr_id:
            qr_img = download_image(mmqr_id)
            if qr_img:
                st.image(qr_img.resize((250, 250), Image.Resampling.LANCZOS))
        else:
            st.warning("Google Drive ထဲတွင် 'mmqr.jpg' ဖိုင် ရှာမတွေ့ပါ။")

        st.markdown("<h4 style='color:#D70F64; margin-top:10px;'>Kpay/Wave Pay: 09450020169 (ZAR ZAR SOE)</h4>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)
        
        customer_name = st.text_input("👤 အမည်")
        customer_phone = st.text_input("📞 ဖုန်းနံပါတ်")
        customer_address = st.text_input("🏠 လိပ်စာ")
        
        receipt_file = st.file_uploader("📄 ငွေလွှဲပြေစာ Upload လုပ်ရန်", type=['png', 'jpg', 'jpeg'])

        if st.button("✅ Order တင်မည်", use_container_width=True):
            if not customer_name or not customer_phone:
                st.error("အမည်နှင့် ဖုန်းနံပါတ် ဖြည့်စွက်ပါ။")
            else:
                if receipt_file is not None:
                    file_bytes = receipt_file.read()
                    upload_file_to_drive(file_bytes, f"receipt_{customer_phone}_{receipt_file.name}", receipt_file.type)
                
                st.session_state.last_order_info = {
                    'cart': st.session_state.cart.copy(),
                    'name': customer_name
                }
                st.session_state.checkout_step = 'success'
                st.rerun()

    elif st.session_state.checkout_step == 'success':
        st.markdown("<div style='text-align:center;'>", unsafe_allow_html=True)
        st.success("🎉 မှာယူမှုအောင်မြင်ပါသည်။ ငွေလက်ခံရရှိမှုကို စစ်ဆေးပြီး ၅ ရက်အတွင်း ပို့ပေးပါမည်။ ကျေးဇူးတင်ပါသည်။")
        st.balloons()

        if st.session_state.last_order_info:
            for item in st.session_state.last_order_info['cart']:
                st.markdown(f"<div class='shop-card'>", unsafe_allow_html=True)
                if item.get('snapshot_bytes'):
                    st.image(Image.open(io.BytesIO(item['snapshot_bytes'])), width=220)
                st.write(f"• **T-Shirt:** {item['tshirt']}")
                st.write(f"• **Sticker:** [{item['sticker_category']}] {item['sticker_name']}")
                st.write(f"• **အရေအတွက် (Quantity):** {item['qty']} ထည်")
                
                if item.get('snapshot_bytes'):
                    st.download_button(
                        label="📥 Save Photo",
                        data=item['snapshot_bytes'],
                        file_name=f"custom_tshirt_{item['tshirt']}_{item['sticker_name']}.png",
                        mime="image/png",
                        key=f"download_{item['tshirt']}_{item['sticker_name']}"
                    )
                st.markdown("</div>", unsafe_allow_html=True)
        
        if st.button("🔄 အသစ်ထပ်မှာမည်", use_container_width=True):
            st.session_state.cart = []
            st.session_state.selected_sticker = None
            st.session_state.last_order_info = None
            st.session_state.checkout_step = 'customizer'
            st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
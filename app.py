import streamlit as st
import sqlite3
import hashlib
import pandas as pd
import requests

# ==========================================
# 1. DATABASE CONFIGURATION & CORE FUNCTIONS
# ==========================================
DB_NAME = "wealth_architect.db"

def init_db():
    """Membaca dan membuat tabel jika belum ada."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    
    # Tabel Users
    c.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL
        )
    ''')
    
    # Tabel User Settings
    c.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            api_key TEXT,
            preferred_model TEXT DEFAULT 'gemini-2.5-flash-preview-09-2025',
            savings_target_pct INTEGER DEFAULT 10,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Tabel Main Data (Financial Records)
    c.execute('''
        CREATE TABLE IF NOT EXISTS financial_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            date DATE NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            type TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    # Tabel AI Reports
    c.execute('''
        CREATE TABLE IF NOT EXISTS ai_reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            content TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    ''')
    
    conn.commit()
    conn.close()

def add_financial_record(user_id, date, description, category, amount, record_type):
    """Menambahkan record keuangan ke database."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT INTO financial_records (user_id, date, description, category, amount, type)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (user_id, date, description, category, amount, record_type))
    conn.commit()
    conn.close()

def get_financial_records(user_id):
    """Mengambil semua record keuangan milik user tertentu."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        SELECT id, date, description, category, amount, type 
        FROM financial_records 
        WHERE user_id = ? 
        ORDER BY date DESC
    ''', (user_id,))
    data = c.fetchall()
    conn.close()
    return data

def delete_financial_record(record_id, user_id):
    """Menghapus record keuangan berdasarkan ID dan User ID."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('DELETE FROM financial_records WHERE id = ? AND user_id = ?', (record_id, user_id))
    conn.commit()
    conn.close()

def save_ai_report(user_id, content):
    """Menyimpan hasil analisis AI ke database."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('INSERT INTO ai_reports (user_id, content) VALUES (?, ?)', (user_id, content))
    conn.commit()
    conn.close()

def get_ai_reports(user_id):
    """Mengambil riwayat analisis AI user."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT id, created_at, content FROM ai_reports WHERE user_id = ? ORDER BY created_at DESC', (user_id,))
    data = c.fetchall()
    conn.close()
    return data

def generate_financial_summary_text(user_id, savings_pct):
    """Menghasilkan teks ringkasan untuk prompt AI."""
    records = get_financial_records(user_id)
    if not records:
        return None
        
    df = pd.DataFrame(records, columns=['ID', 'Tanggal', 'Deskripsi', 'Kategori', 'Jumlah', 'Tipe'])
    
    total_income = df[(df['Tipe'] == 'Credit') & (df['Kategori'] == 'Income')]['Jumlah'].sum()
    total_self_pay = df[(df['Tipe'] == 'Debit') & (df['Kategori'] == 'Self-Pay')]['Jumlah'].sum()
    total_bills = df[(df['Tipe'] == 'Debit') & (df['Kategori'] == 'Bills')]['Jumlah'].sum()
    total_daily = df[(df['Tipe'] == 'Debit') & (df['Kategori'] == 'Daily')]['Jumlah'].sum()
    
    current_balance = total_income - (total_self_pay + total_bills + total_daily)
    target_saving = total_income * (savings_pct / 100)
    
    # Prompt Template
    prompt = f"""
Sebagai 'The Wealth Architect', analisislah ringkasan data keuangan berikut:

- Total Pemasukan: Rp {total_income:,.0f}
- Target Tabungan Wajib ({savings_pct}%): Rp {target_saving:,.0f}
- Realisasi Tabungan (Self-Pay): Rp {total_self_pay:,.0f}
- Pengeluaran Tagihan Wajib: Rp {total_bills:,.0f}
- Pengeluaran Harian Lainnya: Rp {total_daily:,.0f}
- Sisa Saldo Tersedia: Rp {current_balance:,.0f}

Tugas Anda:
1. Evaluasi apakah pengguna disiplin melakukan 'Pay Yourself First'. Berikan pujian jika ya, atau teguran keras jika belum.
2. Deteksi apakah ada indikasi 'Hukum Parkinson' (menghamburkan sisa saldo karena merasa masih punya uang).
3. Berikan rekomendasi langkah spesifik (actionable) untuk mengamankan sisa saldo saat ini.

Berikan jawaban yang profesional, ringkas, tegas, dan mudah dipahami.
"""
    return prompt.strip()

def get_ai_analysis(prompt, api_key, model):
    """Memanggil OpenRouter API untuk mendapatkan analisis AI."""
    if not api_key:
        return "Error: API Key OpenRouter belum diatur."
        
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Anda adalah konsultan keuangan ahli yang tegas, objektif, dan solutif."},
            {"role": "user", "content": prompt}
        ]
    }
    try:
        response = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=data)
        response.raise_for_status()
        result = response.json()
        return result['choices'][0]['message']['content']
    except Exception as e:
        return f"⚠️ Terjadi kesalahan saat menghubungi AI:\n{str(e)}"

# ==========================================
# 2. AUTHENTICATION FUNCTIONS
# ==========================================
def make_hashes(password):
    """Membuat hash SHA-256 untuk password."""
    return hashlib.sha256(str.encode(password)).hexdigest()

def check_hashes(password, hashed_text):
    """Mengecek apakah password cocok dengan hash."""
    if make_hashes(password) == hashed_text:
        return hashed_text
    return False

def add_user(username, password):
    """Menambahkan user baru ke database."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    try:
        hashed_pw = make_hashes(password)
        c.execute('INSERT INTO users(username, password) VALUES (?,?)', (username, hashed_pw))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False # Username sudah ada
    finally:
        conn.close()

def login_user(username, password):
    """Mengecek kredensial user untuk login."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    hashed_pw = make_hashes(password)
    c.execute('SELECT id, username FROM users WHERE username = ? AND password = ?', (username, hashed_pw))
    data = c.fetchone()
    conn.close()
    return data # Returns (id, username) or None

def get_user_settings(user_id):
    """Mengambil pengaturan user."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('SELECT api_key, preferred_model, savings_target_pct FROM user_settings WHERE user_id = ?', (user_id,))
    data = c.fetchone()
    conn.close()
    return data

def update_user_settings(user_id, api_key, preferred_model, savings_target_pct):
    """Memperbarui atau memasukkan pengaturan user."""
    conn = sqlite3.connect(DB_NAME)
    c = conn.cursor()
    c.execute('''
        INSERT OR REPLACE INTO user_settings (user_id, api_key, preferred_model, savings_target_pct)
        VALUES (?, ?, ?, ?)
    ''', (user_id, api_key, preferred_model, savings_target_pct))
    conn.commit()
    conn.close()

# ==========================================
# 3. SESSION STATE INITIALIZATION
# ==========================================
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_id' not in st.session_state:
    st.session_state['user_id'] = None
if 'username' not in st.session_state:
    st.session_state['username'] = ""

# ==========================================
# 4. MAIN APPLICATION LOGIC & UI
# ==========================================
def main():
    # Inisialisasi Database
    init_db()
    
    # Setup Halaman
    st.set_page_config(page_title="The Wealth Architect", page_icon="🏦", layout="wide")
    
    # --- AREA LOGIN / REGISTER (JIKA BELUM LOGIN) ---
    if not st.session_state['logged_in']:
        st.title("🏦 The Wealth Architect")
        st.subheader("Sistem Manajemen Keuangan 'Pay Yourself First'")
        
        # Menggunakan Tab untuk UI yang lebih rapi
        tab1, tab2 = st.tabs(["Login", "Register"])
        
        with tab1:
            st.write("Silakan Login untuk melanjutkan")
            login_username = st.text_input("Username", key="login_user")
            login_password = st.text_input("Password", type='password', key="login_pass")
            
            if st.button("Login"):
                user_data = login_user(login_username, login_password)
                if user_data:
                    st.success(f"Berhasil Login sebagai {user_data[1]}")
                    st.session_state['logged_in'] = True
                    st.session_state['user_id'] = user_data[0]
                    st.session_state['username'] = user_data[1]
                    st.rerun() # Refresh halaman untuk masuk ke mode logged_in
                else:
                    st.error("Username atau Password salah")
                    
        with tab2:
            st.write("Buat Akun Baru")
            new_user = st.text_input("Username", key="reg_user")
            new_password = st.text_input("Password", type='password', key="reg_pass")
            
            if st.button("Register"):
                if new_user and new_password:
                    if add_user(new_user, new_password):
                        st.success("Akun berhasil dibuat! Silakan Login di tab sebelah.")
                        st.balloons()
                    else:
                        st.error("Username sudah terdaftar. Silakan pilih yang lain.")
                else:
                    st.warning("Username dan Password tidak boleh kosong.")

    # --- AREA DASHBOARD (JIKA SUDAH LOGIN) ---
    else:
        st.sidebar.title(f"Selamat Datang, {st.session_state['username']}!")
        
        # Navigation Menu
        menu = ["Dashboard", "Input Data", "Manage Data", "AI Analysis", "Settings"]
        choice = st.sidebar.radio("Navigasi Menu", menu)
        
        st.sidebar.markdown("---")
        
        # Ping Feature (System Ready)
        st.sidebar.success("✅ System Ready")
        
        # Logout Button
        if st.sidebar.button("Logout"):
            st.session_state['logged_in'] = False
            st.session_state['user_id'] = None
            st.session_state['username'] = ""
            st.rerun()
            
        # --- ROUTING HALAMAN ---
        if choice == "Dashboard":
            st.title(f"Dashboard - {st.session_state['username']}")
            
            # Ambil data dari database dan settings
            records = get_financial_records(st.session_state['user_id'])
            current_settings = get_user_settings(st.session_state['user_id'])
            savings_pct = current_settings[2] if current_settings and current_settings[2] else 10
            
            if records:
                # Konversi ke DataFrame Pandas untuk mempermudah perhitungan
                df = pd.DataFrame(records, columns=['ID', 'Tanggal', 'Deskripsi', 'Kategori', 'Jumlah', 'Tipe'])
                
                # Kalkulasi Data
                total_income = df[(df['Tipe'] == 'Credit') & (df['Kategori'] == 'Income')]['Jumlah'].sum()
                total_self_pay = df[(df['Tipe'] == 'Debit') & (df['Kategori'] == 'Self-Pay')]['Jumlah'].sum()
                total_bills = df[(df['Tipe'] == 'Debit') & (df['Kategori'] == 'Bills')]['Jumlah'].sum()
                total_daily = df[(df['Tipe'] == 'Debit') & (df['Kategori'] == 'Daily')]['Jumlah'].sum()
                
                total_expense = total_self_pay + total_bills + total_daily
                current_balance = total_income - total_expense
                target_self_pay = total_income * (savings_pct / 100)
                
                st.write("### 📊 Ringkasan Keuangan Anda")
                
                # Menampilkan metrik utama
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Total Pendapatan", f"Rp {total_income:,.0f}")
                
                # Logika warna delta: Merah jika di bawah target, Hijau jika sesuai/melebihi
                delta_color = "normal" if total_self_pay >= target_self_pay else "inverse"
                col2.metric("Tabungan (Self-Pay)", f"Rp {total_self_pay:,.0f}", 
                            f"{total_self_pay - target_self_pay:,.0f} vs Target", 
                            delta_color=delta_color)
                            
                col3.metric("Tagihan Wajib", f"Rp {total_bills:,.0f}")
                col4.metric("Sisa Saldo Bebas", f"Rp {current_balance:,.0f}")
                
                st.markdown("---")
                
                # Visualisasi Sederhana Komposisi Alokasi
                st.write("#### Komposisi Alokasi Dana")
                alloc_data = pd.DataFrame({
                    'Kategori': ['Self-Pay', 'Bills', 'Daily', 'Sisa Saldo'],
                    'Jumlah': [total_self_pay, total_bills, total_daily, current_balance if current_balance > 0 else 0]
                })
                # Set index ke Kategori agar label sumbu X rapi di chart
                st.bar_chart(alloc_data.set_index('Kategori'))
                
                # Pengecekan Filosofi "Pay Yourself First"
                st.markdown("---")
                if total_self_pay < target_self_pay:
                    st.warning(f"⚠️ **Peringatan Sistem**: Alokasi 'Self-Pay' Anda masih di bawah target ({savings_pct}%). Segera pindahkan uang Anda ke 'rekening mati' sebelum habis untuk hal lain!")
                else:
                    st.success("🎉 **Luar Biasa**: Anda telah memenuhi target 'Pay Yourself First'. Anda bebas menggunakan sisa saldo Anda tanpa rasa bersalah.")
                    
                # Menambahkan 5 Transaksi Terakhir
                st.markdown("---")
                st.write("#### 📜 5 Transaksi Terakhir")
                recent_df = df.head(5)[['Tanggal', 'Deskripsi', 'Kategori', 'Jumlah', 'Tipe']]
                st.dataframe(recent_df, use_container_width=True, hide_index=True)
                    
            else:
                st.info("Belum ada data keuangan. Silakan mulai catat pemasukan Anda di menu 'Input Data'.")
            
        elif choice == "Input Data":
            st.title("📝 Input Data Keuangan")
            st.write("Catat pemasukan dan alokasi dana Anda di sini.")
            
            # Ambil target persentase tabungan dari settings
            current_settings = get_user_settings(st.session_state['user_id'])
            savings_pct = current_settings[2] if current_settings and current_settings[2] else 10
            
            st.info(f"💡 **Filosofi Pay Yourself First**: Ingat untuk selalu mengalokasikan minimal **{savings_pct}%** dari pendapatan Anda ke kategori 'Self-Pay' (Tabungan/Investasi) sebelum membayar tagihan lainnya.")
            
            tab_income, tab_expense = st.tabs(["💰 Catat Pemasukan", "💸 Catat Alokasi / Pengeluaran"])
            
            with tab_income:
                with st.form("form_income", clear_on_submit=True):
                    inc_date = st.date_input("Tanggal")
                    inc_desc = st.text_input("Sumber Pemasukan (cth: Gaji Bulanan, Bonus)")
                    inc_amount = st.number_input("Jumlah (Rp)", min_value=0.0, step=10000.0)
                    submit_inc = st.form_submit_button("Simpan Pemasukan")
                    
                    if submit_inc:
                        if inc_desc and inc_amount > 0:
                            add_financial_record(st.session_state['user_id'], inc_date, inc_desc, 'Income', inc_amount, 'Credit')
                            
                            # Hitung target tabungan otomatis
                            target_saving = inc_amount * (savings_pct / 100)
                            st.success(f"Pemasukan berhasil dicatat! Target 'Self-Pay' Anda dari nominal ini adalah: **Rp {target_saving:,.0f}**")
                        else:
                            st.warning("Deskripsi dan Jumlah harus diisi dengan benar.")
                            
            with tab_expense:
                with st.form("form_expense", clear_on_submit=True):
                    exp_date = st.date_input("Tanggal Pengeluaran")
                    exp_category = st.selectbox("Kategori Prioritas", ["Self-Pay (Tabungan/Investasi)", "Mandatory Bills (Tagihan Pokok)", "Daily Expenses (Harian)"])
                    exp_desc = st.text_input("Keterangan (cth: Rekening Mati, Listrik, Makan)")
                    exp_amount = st.number_input("Jumlah (Rp)", min_value=0.0, step=10000.0)
                    submit_exp = st.form_submit_button("Simpan Pengeluaran")
                    
                    if submit_exp:
                        if exp_desc and exp_amount > 0:
                            # Parse kategori (ambil teks sebelum kurung)
                            parsed_category = exp_category.split(" ")[0]
                            if parsed_category == "Self-Pay":
                                parsed_category = "Self-Pay"
                            elif parsed_category == "Mandatory":
                                parsed_category = "Bills"
                            else:
                                parsed_category = "Daily"
                                
                            add_financial_record(st.session_state['user_id'], exp_date, exp_desc, parsed_category, exp_amount, 'Debit')
                            st.success(f"Alokasi {parsed_category} berhasil dicatat!")
                        else:
                            st.warning("Keterangan dan Jumlah harus diisi dengan benar.")

        elif choice == "Manage Data":
            st.title("🗄️ Manage Data")
            st.write("Lihat dan kelola semua catatan keuangan Anda di sini.")
            
            # Ambil data dari database
            records = get_financial_records(st.session_state['user_id'])
            
            if records:
                # Ubah ke Pandas DataFrame agar rapi
                df = pd.DataFrame(records, columns=['ID', 'Tanggal', 'Deskripsi', 'Kategori', 'Jumlah (Rp)', 'Tipe (Credit/Debit)'])
                
                # Tampilkan sebagai tabel interaktif Streamlit
                st.dataframe(df, use_container_width=True, hide_index=True)
                
                # Fitur Export CSV
                csv = df.to_csv(index=False).encode('utf-8')
                st.download_button(
                    label="📥 Export Data ke CSV",
                    data=csv,
                    file_name=f"keuangan_{st.session_state['username']}.csv",
                    mime='text/csv',
                )
                
                st.markdown("---")
                st.subheader("Hapus Data")
                with st.form("delete_form"):
                    col1, col2 = st.columns([3, 1])
                    with col1:
                        del_id = st.number_input("Masukkan ID Data yang ingin dihapus", min_value=1, step=1, help="Lihat kolom ID pada tabel di atas.")
                    with col2:
                        st.write("") # Spacer
                        st.write("") # Spacer
                        submit_del = st.form_submit_button("Hapus Data")
                        
                    if submit_del:
                        delete_financial_record(del_id, st.session_state['user_id'])
                        st.success(f"Data dengan ID {del_id} berhasil dihapus!")
                        # Gunakan st.rerun() untuk merefresh tabel
                        st.rerun()
            else:
                st.info("Belum ada data keuangan yang dicatat. Silakan ke menu 'Input Data'.")

        elif choice == "AI Analysis":
            st.title("🤖 AI Wealth Analysis")
            st.write("Dapatkan insight dan strategi finansial dari AI berdasarkan data Anda.")
            
            current_settings = get_user_settings(st.session_state['user_id'])
            api_key = current_settings[0] if current_settings and current_settings[0] else ""
            model = current_settings[1] if current_settings and current_settings[1] else "gemini-2.5-flash-preview-09-2025"
            savings_pct = current_settings[2] if current_settings and current_settings[2] else 10
            
            if not api_key:
                st.warning("⚠️ **Perhatian**: Anda belum mengatur API Key OpenRouter. Silakan masuk ke menu **Settings** terlebih dahulu.")
            
            tab_new, tab_history = st.tabs(["🧠 Analisis Baru", "📚 Riwayat Analisis"])
            
            with tab_new:
                st.info("Sistem mengolah data Anda menjadi ringkasan agar privasi tetap terjaga saat dikirim ke AI.")
                
                prompt_text = generate_financial_summary_text(st.session_state['user_id'], savings_pct)
                
                if prompt_text:
                    with st.expander("📄 Lihat Data yang akan dikirim (Prompt Preview)"):
                        st.text_area("Instruksi ke AI:", prompt_text, height=250, disabled=True)
                    
                    if st.button("🧠 Mulai Analisis AI", type="primary", disabled=not bool(api_key)):
                        with st.spinner(f"AI ({model}) sedang membedah data Anda... Mohon tunggu."):
                            ai_response = get_ai_analysis(prompt_text, api_key, model)
                            
                            # Simpan ke database jika bukan error
                            if not ai_response.startswith("⚠️") and not ai_response.startswith("Error:"):
                                save_ai_report(st.session_state['user_id'], ai_response)
                            
                            st.markdown("### 📊 Hasil Analisis AI")
                            st.markdown("---")
                            st.markdown(ai_response)
                            st.markdown("---")
                            st.success("Analisis selesai dan otomatis disimpan ke riwayat!")
                else:
                    st.info("Belum ada data yang bisa dianalisis. Input data terlebih dahulu di menu 'Input Data'.")
                    
            with tab_history:
                reports = get_ai_reports(st.session_state['user_id'])
                if reports:
                    for r_id, r_date, r_content in reports:
                        with st.expander(f"Laporan Tanggal: {r_date}"):
                            st.markdown(r_content)
                else:
                    st.write("Belum ada riwayat analisis AI.")

        elif choice == "Settings":
            st.title("⚙️ Settings")
            st.write("Konfigurasi akun dan AI Anda di sini.")
            
            # Ambil data settings saat ini
            current_settings = get_user_settings(st.session_state['user_id'])
            current_api_key = current_settings[0] if current_settings and current_settings[0] else ""
            current_model = current_settings[1] if current_settings and current_settings[1] else "gemini-2.5-flash-preview-09-2025"
            current_savings_pct = current_settings[2] if current_settings and current_settings[2] else 10
            
            with st.form("settings_form"):
                st.subheader("1. Konfigurasi 'Pay Yourself First'")
                new_savings_pct = st.number_input("Target Potongan Tabungan Wajib (%)", min_value=1, max_value=100, value=current_savings_pct, help="Berapa persen dari pemasukan yang wajib ditabung di awal?")
                
                st.subheader("2. Konfigurasi AI (OpenRouter)")
                new_api_key = st.text_input("OpenRouter API Key", type="password", value=current_api_key, help="API Key Anda aman dan hanya disimpan di database SQLite lokal Anda.")
                model_options = ["gemini-2.5-flash-preview-09-2025", "openai/gpt-4o-mini", "anthropic/claude-3-haiku"]
                model_idx = model_options.index(current_model) if current_model in model_options else 0
                new_model = st.selectbox("Model AI Prioritas", model_options, index=model_idx)
                
                submit_settings = st.form_submit_button("Simpan Pengaturan")
                
                if submit_settings:
                    update_user_settings(st.session_state['user_id'], new_api_key, new_model, new_savings_pct)
                    st.success("Pengaturan berhasil disimpan!")

if __name__ == '__main__':
    main()
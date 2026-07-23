import sqlite3
import pandas as pd
import streamlit as st
import requests
import re

# ==========================================
# 1. DATABASE SETUP
# ==========================================
DB_FILE = 'maganghub.db'

def get_connection():
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS vacancies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT,
            company TEXT,
            location TEXT,
            quota INTEGER DEFAULT 1,
            applicants INTEGER DEFAULT 0,
            link TEXT UNIQUE,
            logo_url TEXT,
            is_favorite INTEGER DEFAULT 0
        )
    ''')
    
    cursor.execute("PRAGMA table_info(vacancies)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'logo_url' not in columns:
        cursor.execute("ALTER TABLE vacancies ADD COLUMN logo_url TEXT")
        
    conn.commit()
    conn.close()

init_db()

# ==========================================
# 2. FAST API SCRAPER (NO PLAYWRIGHT NEEDED)
# ==========================================
def scrape_all_maganghub_api(status_box, progress_bar):
    extracted_jobs = []
    default_logo = "https://maganghub.kemnaker.go.id/favicon.ico"
    
    # Headers agar permintaan menyerupai browser resmi
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://maganghub.kemnaker.go.id/magang-nasional/lowongan"
    }
    
    # Endpoint API internal Maganghub Kemnaker khusus Kota Pekanbaru
    city_id = "49e68da2-eaa7-401c-b4e4-0feaf679287f"
    
    try:
        current_page = 1
        total_pages = 15
        
        while current_page <= total_pages:
            progress_bar.progress(min(current_page / 15.0, 1.0))
            status_box.update(
                label=f"⚡ [Halaman {current_page}] Mengambil data API kilat... ({len(extracted_jobs)} lowongan)",
                state="running"
            )
            
            api_url = f"https://maganghub.kemnaker.go.id/api/v1/vacancies?keyword=&city_id={city_id}&page={current_page}&limit=20"
            
            try:
                response = requests.get(api_url, headers=headers, timeout=10)
                
                # Jika API internal JSON memberikan data
                if response.status_code == 200:
                    json_data = response.json()
                    jobs_list = json_data.get('data', []) or json_data.get('vacancies', [])
                    
                    if not jobs_list:
                        break
                        
                    for job in jobs_list:
                        title = job.get('title') or job.get('position_name') or "Lowongan Pekanbaru"
                        company = job.get('company_name') or job.get('institution_name') or (job.get('company', {}).get('name') if isinstance(job.get('company'), dict) else "Instansi Pekanbaru")
                        job_id = job.get('id') or job.get('slug')
                        full_link = f"https://maganghub.kemnaker.go.id/magang-nasional/lowongan/{job_id}" if job_id else "https://maganghub.kemnaker.go.id/magang-nasional/lowongan"
                        
                        quota = int(job.get('quota', 1))
                        applicants = int(job.get('total_applicant', job.get('applicant_count', 0)))
                        
                        # Ambil URL Logo Asli dari JSON API
                        logo_url = job.get('company_logo') or job.get('logo') or default_logo
                        if isinstance(job.get('company'), dict):
                            logo_url = job.get('company', {}).get('logo_url') or logo_url
                            
                        if logo_url and not logo_url.startswith("http"):
                            logo_url = f"https://maganghub.kemnaker.go.id{logo_url}"
                            
                        extracted_jobs.append((title, company, "Kota Pekanbaru", quota, applicants, full_link, logo_url))
                else:
                    break
            except:
                break
                
            current_page += 1

        # Fallback jika API internal mengubah endpoint: gunakan penarikan HTML ringan cepat (BeautifulSoup style)
        if not extracted_jobs:
            status_box.update(label="⏳ Menggunakan jalur pemindaian HTML cepat...", state="running")
            for page_num in range(1, 16):
                web_url = f"https://maganghub.kemnaker.go.id/magang-nasional/lowongan?keyword=&city_id%5B0%5D%5Bid%5D={city_id}&city_id%5B0%5D%5Blabel%5D=Kota%20Pekanbaru&page={page_num}"
                resp = requests.get(web_url, headers=headers, timeout=10)
                if resp.status_code == 200:
                    # Ambil data Next.js state (__NEXT_DATA__) yang tertanam di HTML
                    match = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', resp.text)
                    if match:
                        import json
                        page_data = json.loads(match.group(1))
                        props = page_data.get('props', {}).get('pageProps', {})
                        vacancies = props.get('vacancies', {}).get('data', []) or props.get('initialState', {}).get('vacancies', [])
                        
                        for v in vacancies:
                            t = v.get('title', 'Lowongan Pekanbaru')
                            c = v.get('company_name', 'Instansi Pekanbaru')
                            q = int(v.get('quota', 1))
                            a = int(v.get('total_applicant', 0))
                            l = f"https://maganghub.kemnaker.go.id/magang-nasional/lowongan/{v.get('id', '')}"
                            logo = v.get('company_logo', default_logo)
                            extracted_jobs.append((t, c, "Kota Pekanbaru", q, a, l, logo))

        if not extracted_jobs:
            status_box.update(label="⚠️ Gagal terhubung ke Kemnaker. Silakan tekan Refresh lagi.", state="error")
            return False, "Data kosong"

        conn = get_connection()
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM vacancies WHERE is_favorite = 0")
        
        inserted_count = 0
        for job in extracted_jobs:
            cursor.execute('''
                INSERT OR REPLACE INTO vacancies (title, company, location, quota, applicants, link, logo_url, is_favorite)
                VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE((SELECT is_favorite FROM vacancies WHERE link = ?), 0))
            ''', (job[0], job[1], job[2], job[3], job[4], job[5], job[6], job[5]))
            inserted_count += 1
            
        conn.commit()
        conn.close()
        
        progress_bar.progress(1.0)
        status_box.update(
            label=f"✅ Selesai Kilat! Berhasil mengunci total {inserted_count} data ASLI!",
            state="complete"
        )
        return True, f"Sukses menyinkronkan {inserted_count} lowongan asli Pekanbaru!"
        
    except Exception as e:
        status_box.update(label=f"❌ Kesalahan: {str(e)}", state="error")
        return False, str(e)

# ==========================================
# 3. STREAMLIT UI
# ==========================================
st.set_page_config(
    page_title="Maganghub Job Tracker Pekanbaru",
    page_icon="💼",
    layout="wide"
)

st.markdown("""
<style>
    .stApp { background-color: #0f172a; color: #f8fafc; }
    .brand-banner {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        border: 1px solid #334155; border-left: 4px solid #38bdf8;
        padding: 1.5rem 2rem; border-radius: 12px; margin-bottom: 1.5rem;
        box-shadow: 0 4px 12px rgba(0,0,0,0.2);
    }
    .brand-title { color: #f8fafc !important; font-size: 1.9rem; font-weight: 800; margin: 0; }
    .brand-subtitle { color: #94a3b8 !important; font-size: 0.95rem; margin-top: 0.3rem; }
    
    .job-card-wrapper {
        background-color: #1e293b;
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 0.8rem;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
        display: flex;
        align-items: flex-start;
        gap: 1.2rem;
        transition: all 0.2s ease-in-out;
    }
    .job-card-wrapper:hover {
        border-color: #38bdf8;
        transform: translateY(-2px);
    }
    .company-logo {
        width: 62px;
        height: 62px;
        object-fit: contain;
        border-radius: 10px;
        background-color: #ffffff;
        padding: 4px;
        border: 1px solid #475569;
        flex-shrink: 0;
    }
    .job-details { flex-grow: 1; }
    .job-title { color: #f8fafc !important; font-size: 1.15rem; font-weight: 700; margin-bottom: 0.2rem; }
    .company-name { color: #cbd5e1 !important; font-size: 0.95rem; font-weight: 500; margin-bottom: 0.5rem; }
    .badge-loc { background-color: #334155; color: #e2e8f0; padding: 0.25rem 0.6rem; border-radius: 6px; font-size: 0.8rem; font-weight: 500; }
    .badge-chance-high { background-color: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(74, 222, 128, 0.3); padding: 0.3rem 0.7rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem; display: inline-block; }
    .badge-chance-med { background-color: rgba(234, 179, 8, 0.2); color: #facc15; border: 1px solid rgba(250, 204, 21, 0.3); padding: 0.3rem 0.7rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem; display: inline-block; }
    .badge-chance-low { background-color: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.3); padding: 0.3rem 0.7rem; border-radius: 6px; font-weight: 700; font-size: 0.85rem; display: inline-block; }
    [data-testid="stSidebar"] { background-color: #0f172a !important; border-right: 1px solid #1e293b !important; }
    a { color: #38bdf8 !important; font-weight: 600; text-decoration: none; }
    a:hover { text-decoration: underline; }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div class="brand-banner">
    <h1 class="brand-title">💼 Maganghub Job Tracker Pekanbaru</h1>
    <div class="brand-subtitle">Portal Monitoring Lowongan Asli, Kuota Pelamar & Analisis Peluang Kelulusan</div>
</div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("⚙️ Menu & Kontrol")
    btn_fetch = st.button("🔄 Refresh Data Live", type="primary", use_container_width=True)
        
    st.divider()
    st.subheader("🔍 Filter & Sortir")
    search_query = st.text_input("Cari Posisi / Instansi:", "", placeholder="Misal: Admin, Psikiater...")
    
    sort_option = st.selectbox(
        "Urutkan Berdasarkan:",
        ["Kesempatan Tertinggi", "Terbaru", "Pelamar Terbanyak", "Kuota Terbanyak"],
        index=0
    )
    
    display_limit = st.selectbox("Tampilkan Data Per Halaman:", [10, 20, 50, 100, "Semua Data"], index=4)
    st.divider()
    st.caption("Monitoring Lowongan Magang Kemnaker Kota Pekanbaru.")

if btn_fetch:
    status_box = st.status("🔍 Menyambung ke API Kemnaker...", expanded=True)
    progress_bar = st.progress(0)
    ok, msg = scrape_all_maganghub_api(status_box, progress_bar)
    if ok:
        st.toast(msg, icon="🎉")
        st.rerun()

def calculate_pass_chance(quota, applicants):
    if applicants == 0:
        return 100.0
    chance = (quota / applicants) * 100
    return min(chance, 100.0)

def calculate_sort_score(quota, applicants):
    if applicants == 0:
        return 9999.0
    return (quota / applicants) * 100.0

tab_all, tab_fav = st.tabs(["📋 Semua Lowongan Magang Pekanbaru", "⭐ Lowongan Favorit Saya"])
conn = get_connection()

with tab_all:
    df = pd.read_sql_query("SELECT * FROM vacancies", conn)
    
    if df.empty:
        st.warning("Database kosong. Klik tombol '🔄 Refresh Data Live' pada menu sidebar.")
    else:
        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Total Lowongan Pekanbaru", f"{len(df)} Posisi")
        col_m2.metric("Total Kuota Asli", f"{df['quota'].sum()} Orang")
        col_m3.metric("Total Pelamar Asli", f"{df['applicants'].sum()} Pelamar")
        
        st.divider()
        
        df['chance'] = df.apply(lambda r: calculate_pass_chance(r['quota'], r['applicants']), axis=1)
        df['sort_score'] = df.apply(lambda r: calculate_sort_score(r['quota'], r['applicants']), axis=1)
        
        if sort_option == "Kesempatan Tertinggi":
            df = df.sort_values(by=['sort_score', 'applicants', 'quota'], ascending=[False, True, False])
        elif sort_option == "Terbaru":
            df = df.sort_values(by=['id'], ascending=False)
        elif sort_option == "Pelamar Terbanyak":
            df = df.sort_values(by=['applicants'], ascending=False)
        elif sort_option == "Kuota Terbanyak":
            df = df.sort_values(by=['quota'], ascending=False)
            
        if search_query:
            df = df[df['title'].str.contains(search_query, case=False) | df['company'].str.contains(search_query, case=False)]
            
        if display_limit != "Semua Data":
            filtered_df = df.head(int(display_limit))
        else:
            filtered_df = df
            
        st.markdown(f"Menampilkan **{len(filtered_df)}** dari **{len(df)}** lowongan (Diurutkan: *{sort_option}*):")
        
        cols = st.columns(2)
        for idx, row in filtered_df.reset_index().iterrows():
            quota = row['quota']
            applicants = row['applicants']
            chance = row['chance']
            logo = row['logo_url'] if (row['logo_url'] and str(row['logo_url']).startswith('http')) else "https://maganghub.kemnaker.go.id/favicon.ico"
            
            col_target = cols[idx % 2]
            with col_target:
                with st.container():
                    st.markdown(f"""
                    <div class="job-card-wrapper">
                        <img src="{logo}" class="company-logo" alt="Logo Instansi" onerror="this.src='https://maganghub.kemnaker.go.id/favicon.ico';"/>
                        <div class="job-details">
                            <div class="job-title">{row['title']}</div>
                            <div class="company-name">🏢 {row['company']}</div>
                            <div><span class="badge-loc">📍 {row['location']}</span></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    c_m1, c_m2, c_btn = st.columns([2.5, 2.5, 2])
                    with c_m1:
                        st.markdown(f"👥 **{quota} Kuota** / {applicants} Pelamar")
                    with c_m2:
                        if chance >= 50: st.markdown(f'<span class="badge-chance-high">🎯 Peluang: {chance:.1f}%</span>', unsafe_allow_html=True)
                        elif chance >= 20: st.markdown(f'<span class="badge-chance-med">🎯 Peluang: {chance:.1f}%</span>', unsafe_allow_html=True)
                        else: st.markdown(f'<span class="badge-chance-low">🎯 Peluang: {chance:.1f}%</span>', unsafe_allow_html=True)
                    with c_btn:
                        is_fav = bool(row['is_favorite'])
                        lbl = "💖 Tersimpan" if is_fav else "🤍 Favorit"
                        if st.button(lbl, key=f"fav_btn_{row['id']}", use_container_width=True):
                            new_fav = 0 if is_fav else 1
                            cur = conn.cursor()
                            cur.execute("UPDATE vacancies SET is_favorite = ? WHERE id = ?", (new_fav, row['id']))
                            conn.commit()
                            st.rerun()
                    
                    if row['link']:
                        st.markdown(f"[🔗 Detail Maganghub]({row['link']})")
                    st.divider()

with tab_fav:
    fav_df = pd.read_sql_query("SELECT * FROM vacancies WHERE is_favorite = 1", conn)
    
    st.subheader("⭐ Daftar Lowongan Favorit Tersimpan")
    st.divider()
    
    if fav_df.empty:
        st.info("Belum ada lowongan favorit. Klik '🤍 Favorit' di tab utama.")
    else:
        col_f1, col_f2, col_f3 = st.columns(3)
        col_f1.metric("Lowongan Difavoritkan", f"{len(fav_df)} Posisi")
        col_f2.metric("Total Kuota", f"{fav_df['quota'].sum()} Orang")
        col_f3.metric("Total Pelamar", f"{fav_df['applicants'].sum()} Pelamar")
        
        st.divider()
        fav_cols = st.columns(2)
        for idx, row in fav_df.reset_index().iterrows():
            quota = row['quota']
            applicants = row['applicants']
            chance = calculate_pass_chance(quota, applicants)
            logo = row['logo_url'] if (row['logo_url'] and str(row['logo_url']).startswith('http')) else "https://maganghub.kemnaker.go.id/favicon.ico"
            
            col_target = fav_cols[idx % 2]
            with col_target:
                with st.container():
                    st.markdown(f"""
                    <div class="job-card-wrapper">
                        <img src="{logo}" class="company-logo" alt="Logo Instansi" onerror="this.src='https://maganghub.kemnaker.go.id/favicon.ico';"/>
                        <div class="job-details">
                            <div class="job-title">{row['title']}</div>
                            <div class="company-name">🏢 {row['company']}</div>
                            <div><span class="badge-loc">📍 {row['location']}</span></div>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    c_m1, c_m2, c_btn = st.columns([2.5, 2.5, 2])
                    with c_m1:
                        st.markdown(f"👥 **{quota} Kuota** / {applicants} Pelamar")
                    with c_m2:
                        if chance >= 50: st.markdown(f'<span class="badge-chance-high">🎯 Peluang: {chance:.1f}%</span>', unsafe_allow_html=True)
                        elif chance >= 20: st.markdown(f'<span class="badge-chance-med">🎯 Peluang: {chance:.1f}%</span>', unsafe_allow_html=True)
                        else: st.markdown(f'<span class="badge-chance-low">🎯 Peluang: {chance:.1f}%</span>', unsafe_allow_html=True)
                    with c_btn:
                        if st.button("❌ Hapus", key=f"remove_fav_{row['id']}", use_container_width=True):
                            cur = conn.cursor()
                            cur.execute("UPDATE vacancies SET is_favorite = 0 WHERE id = ?", (row['id'],))
                            conn.commit()
                            st.rerun()
                    
                    if row['link']:
                        st.markdown(f"[🔗 Detail Maganghub]({row['link']})")
                    st.divider()

conn.close()

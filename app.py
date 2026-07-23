import sqlite3
import pandas as pd
import streamlit as st
import re
import os
from playwright.sync_api import sync_playwright

# 1. PERINTAH OTOMATIS INSTALL CHROMIUM DI LINUX CLOUD
os.system("playwright install chromium")

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
# 2. ULTRA-STABLE PLAYWRIGHT SCRAPER
# ==========================================
def scrape_all_225_maganghub_stable(status_box, progress_bar):
    base_url = "https://maganghub.kemnaker.go.id/magang-nasional/lowongan?keyword=&city_id%5B0%5D%5Bid%5D=49e68da2-eaa7-401c-b4e4-0feaf679287f&city_id%5B0%5D%5Blabel%5D=Kota%20Pekanbaru"
    extracted_jobs = []
    seen_links = set()
    default_logo = "https://maganghub.kemnaker.go.id/favicon.ico"
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            current_page = 1
            max_pages = 20
            empty_page_streak = 0
            
            while current_page <= max_pages:
                progress_percent = min(current_page / 15.0, 1.0)
                progress_bar.progress(progress_percent)
                status_box.update(
                    label=f"⏳ [Halaman {current_page}] Menyapu & mengunci seluruh kartu... ({len(extracted_jobs)} lowongan unik)",
                    state="running"
                )
                
                page_url = f"{base_url}&page={current_page}" if current_page > 1 else base_url
                page.goto(page_url, timeout=40000, wait_until="domcontentloaded")
                
                try:
                    page.wait_for_selector("a[href*='/lowongan/']", state="visible", timeout=8000)
                except:
                    empty_page_streak += 1
                    if empty_page_streak >= 2:
                        break
                    current_page += 1
                    continue
                
                for i in range(5):
                    page.evaluate(f"window.scrollTo(0, {i * 400});")
                    page.wait_for_timeout(300)
                page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                page.wait_for_timeout(800)
                
                links = page.query_selector_all("a[href*='/lowongan/']")
                
                if len(links) < 15 and current_page < 13:
                    page.wait_for_timeout(1500)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    links = page.query_selector_all("a[href*='/lowongan/']")
                
                if not links:
                    empty_page_streak += 1
                    if empty_page_streak >= 2:
                        break
                    current_page += 1
                    continue
                
                empty_page_streak = 0
                new_items_in_this_page = 0
                
                for index, a_tag in enumerate(links):
                    href = a_tag.get_attribute("href") or ""
                    text_content = a_tag.inner_text().strip()
                    
                    if text_content and len(text_content) > 3 and "Reset" not in text_content and "Kembali" not in text_content:
                        full_link = f"https://maganghub.kemnaker.go.id{href}" if href.startswith("/") else href
                        
                        if full_link in seen_links:
                            continue
                        
                        lines = [line.strip() for line in text_content.split("\n") if line.strip()]
                        title = lines[0] if len(lines) > 0 else f"Lowongan Pekanbaru #{len(extracted_jobs)+1}"
                        company = lines[1] if len(lines) > 1 else "Instansi Pekanbaru"
                        
                        quota_match = re.search(r'Kuota\s*:\s*(\d+)', text_content, re.IGNORECASE)
                        pelamar_match = re.search(r'Pelamar\s*:\s*(\d+)', text_content, re.IGNORECASE)
                        
                        real_quota = int(quota_match.group(1)) if quota_match else 1
                        real_applicants = int(pelamar_match.group(1)) if pelamar_match else 0
                        
                        logo_url = default_logo
                        try:
                            img_elem = a_tag.query_selector("img")
                            if img_elem:
                                src = img_elem.get_attribute("src") or img_elem.get_attribute("data-src") or img_elem.get_attribute("srcset")
                                if src:
                                    src_clean = src.split(" ")[0]
                                    logo_url = src_clean if src_clean.startswith("http") else f"https://maganghub.kemnaker.go.id{src_clean}"
                        except:
                            pass
                        
                        seen_links.add(full_link)
                        extracted_jobs.append((title, company, "Kota Pekanbaru", real_quota, real_applicants, full_link, logo_url))
                        new_items_in_this_page += 1
                
                current_page += 1
            
            browser.close()
            
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
            label=f"✅ Selesai 100%! Berhasil mengunci total {inserted_count} data ASLI tanpa ada yang terlewat!",
            state="complete"
        )
        return True, f"Sukses menyinkronkan total {inserted_count} lowongan asli Pekanbaru!"
        
    except Exception as e:
        status_box.update(label=f"❌ Terjadi kesalahan jaringan/timeout: {str(e)}", state="error")
        return False, str(e)

def refresh_favorites_live():
    conn = get_connection()
    fav_df = pd.read_sql_query("SELECT id, link FROM vacancies WHERE is_favorite = 1", conn)
    conn.close()
    
    if fav_df.empty:
        return False, "Tidak ada lowongan favorit untuk diperbarui."
        
    updated_count = 0
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            conn = get_connection()
            cursor = conn.cursor()
            
            for idx, row in fav_df.iterrows():
                link = row['link']
                if link:
                    page.goto(link, timeout=20000, wait_until="domcontentloaded")
                    page.wait_for_timeout(1200)
                    
                    body_text = page.locator("body").inner_text()
                    pelamar_match = re.search(r'(?:Pelamar|Pendaftar)\s*:\s*(\d+)', body_text, re.IGNORECASE)
                    
                    if pelamar_match:
                        real_live_applicants = int(pelamar_match.group(1))
                        cursor.execute("UPDATE vacancies SET applicants = ? WHERE id = ?", (real_live_applicants, row['id']))
                        updated_count += 1
                    
            conn.commit()
            conn.close()
            browser.close()
            
        return True, f"🔥 Berhasil memperbarui data pelamar asli pada {updated_count} lowongan favorit!"
    except Exception as e:
        return False, f"Gagal merefresh favorit: {str(e)}"

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
    status_box = st.status("🔍 Menghubungkan & menyapu data Maganghub...", expanded=True)
    progress_bar = st.progress(0)
    ok, msg = scrape_all_225_maganghub_stable(status_box, progress_bar)
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
    
    col_fav_title, col_fav_refresh = st.columns([4, 1.5])
    with col_fav_title:
        st.subheader("⭐ Daftar Lowongan Favorit Tersimpan")
    with col_fav_refresh:
        if st.button("🔄 Refresh Pelamar Asli", type="primary", use_container_width=True):
            with st.spinner("Mengambil jumlah pelamar asli terkini dari Maganghub..."):
                ok, msg = refresh_favorites_live()
                if ok:
                    st.toast(msg, icon="⚡")
                else:
                    st.warning(msg)
                st.rerun()
                
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
import streamlit as st
import pandas as pd
import requests
import time
import io
from rapidfuzz import fuzz

# ==========================================
# 1. FUNGSI PENCARIAN
# ==========================================
def cari_data_via_nspp(nspp):
    # Simulasi database internal Kemenag
    mock_db = {
        "12345": {"jalan": "Jl. Kyai Haji Hasyim Ashari No. 10", "desa": "Karanganyar", "kec": "Karanganyar"},
        "67890": {"jalan": "Jl. Raya Bogor KM 30", "desa": "Cimanggis", "kec": "Cimanggis"}
    }
    return mock_db.get(str(nspp), None)

def cari_osm(nama_pesantren, kecamatan, kabupaten):
    headers = {'User-Agent': 'AplikasiGeocodingPesantren/1.0 (emailanda@example.com)'}
    # Jika kecamatan tidak ada, cari hanya berdasarkan nama dan kabupaten
    query = f"{nama_pesantren}, {kecamatan}, {kabupaten}" if kecamatan else f"{nama_pesantren}, {kabupaten}"
    url = f"https://nominatim.openstreetmap.org/search?q={query}&format=json&addressdetails=1&limit=3"
    
    try:
        response = requests.get(url, headers=headers)
        data = response.json()
        
        if data:
            hasil_terbaik = data[0]
            lat = hasil_terbaik.get('lat')
            lon = hasil_terbaik.get('lon')
            alamat_detail = hasil_terbaik.get('address', {})
            
            jalan = alamat_detail.get('road', '')
            desa = alamat_detail.get('village', alamat_detail.get('suburb', ''))
            kec_ditemukan = alamat_detail.get('county', alamat_detail.get('city_district', '')) # Ekstrak kecamatan dari OSM
            nama_osm = hasil_terbaik.get('name', '')
            
            kemiripan = fuzz.partial_ratio(str(nama_pesantren).lower(), str(nama_osm).lower())
            
            if kemiripan > 75:
                return {"lat": lat, "lon": lon, "jalan": jalan, "desa": desa, "kecamatan": kec_ditemukan, "sumber": "OSM"}
            else:
                return {"lat": None, "lon": None, "jalan": "", "desa": "", "kecamatan": "", "sumber": "OSM (Nama Tidak Cocok)"}
        else:
            return {"lat": None, "lon": None, "jalan": "", "desa": "", "kecamatan": "", "sumber": "Tidak Ditemukan di OSM"}
            
    except Exception as e:
        return {"lat": None, "lon": None, "jalan": "", "desa": "", "kecamatan": "", "sumber": "Error API"}

# ==========================================
# 2. UI STREAMLIT
# ==========================================
st.set_page_config(page_title="AI Geocoding Pesantren", page_icon="🕌", layout="wide")

st.title("AI Geocoding & Pelengkap Alamat Pesantren")
st.write("Aplikasi ini akan membaca data Excel/CSV Anda, lalu mencari alamat yang hilang (Jalan & Desa) berdasarkan **NSPP** atau **OpenStreetMap (OSM)**.")

# Upload File
uploaded_file = st.file_uploader("Upload File Data Anda (.csv atau .xlsx)", type=['csv', 'xlsx'])

if uploaded_file is not None:
    # Membaca data
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
            
        st.write("**Preview Data Awal:**")
        st.dataframe(df.head())

        kolom_wajib = ['PROVINSI','KOTA/KAB.', 'NO.STATISTIK', 'NAMA LEMBAGA']
        kolom_ada = all(kolom in df.columns for kolom in kolom_wajib)

        if not kolom_ada:
            st.error(f"File Anda harus memiliki kolom: {', '.join(kolom_wajib)}")
        else:
            if st.button("Mulai Proses Pengayaan Data"):
                hasil_pengayaan = []
                total_data = len(df)
                
                # Setup Progress Bar
                progress_bar = st.progress(0)
                status_text = st.empty()

                for index, row in df.iterrows():
                    PROV = str(row['PROVINSI']).strip()
                    kab = str(row['KOTA/KAB.']).strip()
                    nspp = str(row['NO.STATISTIK']).strip()
                    nama = str(row['NAMA LEMBAGA']).strip()
                    
                    # Mengambil kecamatan jika kolomnya ada di DataFrame, jika tidak kosongkan
                    kec = str(row['KECAMATAN']).strip() if 'KECAMATAN' in df.columns else ""
                    
                    status_text.text(f"Memproses {index + 1}/{total_data}: {nama}...")
                    
                    # Logika pencarian
                    data_nspp = cari_data_via_nspp(nspp)
                    
                    if data_nspp:
                        jalan = data_nspp['jalan']
                        desa = data_nspp['desa']
                        kecamatan_ditemukan = data_nspp['kec']
                        sumber = "Database Resmi / NSPP"
                        lat, lon = None, None 
                    else:
                        data_osm = cari_osm(nama, kec, kab)
                        jalan = data_osm['jalan']
                        desa = data_osm['desa']
                        kecamatan_ditemukan = data_osm['kecamatan']
                        lat = data_osm['lat']
                        lon = data_osm['lon']
                        sumber = data_osm['sumber']
                        time.sleep(1) # Rate limit OSM
                        
                    baris_hasil = row.to_dict()
                    baris_hasil.update({
                        "Jalan_Ditemukan": jalan,
                        "Desa_Ditemukan": desa,
                        "Kecamatan_Ditemukan": kecamatan_ditemukan,
                        "Latitude": lat,
                        "Longitude": lon,
                        "Sumber_Data": sumber
                    })
                    hasil_pengayaan.append(baris_hasil)
                    
                    # Update Progress Bar
                    progress_bar.progress((index + 1) / total_data)

                status_text.text("Proses Selesai!")
                df_hasil = pd.DataFrame(hasil_pengayaan)
                
                st.write("**Hasil Pengayaan Data:**")
                st.dataframe(df_hasil)

                # Export File di Memory agar bisa didownload
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_hasil.to_excel(writer, index=False, sheet_name='Sheet1')
                proses_excel = output.getvalue()

                st.download_button(
                    label="Download Hasil (Excel)",
                    data=proses_excel,
                    file_name=f"Hasil_Lengkap_{uploaded_file.name.split('.')[0]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

    except Exception as e:
        st.error(f"Terjadi kesalahan saat membaca file: {e}")

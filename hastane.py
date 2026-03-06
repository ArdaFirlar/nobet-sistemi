import os
import calendar
from datetime import datetime, date
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from supabase import create_client, Client
from dotenv import load_dotenv
from ortools.sat.python import cp_model

# 1. Çevre Değişkenlerini (Şifreleri) Yükle
load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("HATA: .env dosyasında SUPABASE_URL veya SUPABASE_KEY bulunamadı!")

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. FastAPI Uygulamasını ve İzinleri (CORS) Başlat
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Netlify vb. her yerden gelen isteklere izin ver
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. İletişim Modelleri (Frontend'den gelecek verilerin yapısı)
class IzinIstegi(BaseModel):
    doktor_id: int
    tarihler: List[str]

class GuncelleIstegi(BaseModel):
    doktor_id: int
    idler: List[int]

class YeniListeIstegi(BaseModel):
    yil: int
    ay: int

class GunduzMesaisiIstegi(BaseModel):
    tarih: str
    istasyon_id: int
    doktor_idler: List[int]

class YeniIstasyon(BaseModel):
    isim: str
    nobete_engel_mi: bool

class YeniDoktor(BaseModel):
    isim: str
    kidem: str
    rol: str
    muaf_mi: bool

class OncekiAyDevir(BaseModel):
    doktor_id: int
    gun_tipi: str

# 4. Veritabanı Yönetim Sınıfı
class HastaneSistemi:
    def __init__(self):
        self.doktorlar = []
        self.istasyonlar = []
        self.izinler = []
        self.istenmeyenler = []
        self.gunduz_mesaileri = []
        self.onceki_ay_nobetleri = []

    def veritabanindan_yukle(self, db: Client):
        self.doktorlar = db.table("doktorlar").select("*").execute().data
        self.istasyonlar = db.table("istasyonlar").select("*").execute().data
        self.izinler = db.table("izinli_gunler").select("*").execute().data
        self.istenmeyenler = db.table("istenmeyen_kisiler").select("*").execute().data
        self.gunduz_mesaileri = db.table("gunduz_mesaileri").select("*").execute().data
        self.onceki_ay_nobetleri = db.table("onceki_ay_nobetleri").select("*").execute().data

# Sistemi ayağa kaldırırken ilk verileri çek
hastane = HastaneSistemi()
hastane.veritabanindan_yukle(supabase_client)

GUN_ISIMLERI = {0: "Pzt", 1: "Sal", 2: "Çar", 3: "Per", 4: "Cum", 5: "Cmt", 6: "Paz"}


# ==========================================
# 5. API UÇ NOKTALARI (ENDPOINTS)
# ==========================================

@app.get("/api/doktorlar")
def get_doktorlar():
    # Doktorları A'dan Z'ye isimlerine göre sırala
    sirali_doktorlar = sorted(hastane.doktorlar, key=lambda x: x["isim"])
    return {"basari": True, "data": sirali_doktorlar}

@app.get("/api/istasyonlar")
def get_istasyonlar():
    # İstasyonları A'dan Z'ye isimlerine göre sırala
    sirali_istasyonlar = sorted(hastane.istasyonlar, key=lambda x: x["isim"])
    return {"basari": True, "data": sirali_istasyonlar}

@app.get("/api/doktor-detay/{doktor_id}")
def get_doktor_detay(doktor_id: int):
    # RAM'i tamamen devre dışı bırakıp doğrudan taze veritabanına (Supabase) bakıyoruz!
    izin_sonuc = supabase_client.table("izinli_gunler").select("tarih").eq("doktor_id", doktor_id).execute()
    istenmeyen_sonuc = supabase_client.table("istenmeyen_kisiler").select("istenmeyen_doktor_id").eq("doktor_id", doktor_id).execute()
    
    doktor_izinleri = [iz["tarih"] for iz in izin_sonuc.data] if izin_sonuc.data else []
    doktor_istenmeyenler = [ist["istenmeyen_doktor_id"] for ist in istenmeyen_sonuc.data] if istenmeyen_sonuc.data else []
    
    return {"basari": True, "izinler": doktor_izinleri, "istenmeyenler": doktor_istenmeyenler}

@app.get("/api/mevcut-liste")
def get_mevcut_liste(yil: int, ay: int):
    sonuc = supabase_client.table("aylik_listeler").select("*").eq("yil", yil).eq("ay", ay).execute()
    if sonuc.data and len(sonuc.data) > 0:
        kayit = sonuc.data[0]
        return {"basari": True, "data": kayit["liste_json"], "uyari": kayit.get("uyari_metni")}
    return {"basari": False}

@app.get("/api/gunduz-mesaileri-matris")
def get_matris(yil: int, ay: int):
    matris = {}
    for gm in hastane.gunduz_mesaileri:
        try:
            tarih_obj = datetime.strptime(gm["tarih"], "%Y-%m-%d")
            if tarih_obj.year == yil and tarih_obj.month == ay:
                t_str = gm["tarih"]
                ist_id = gm["istasyon_id"]
                dr_id = gm["doktor_id"]
                if t_str not in matris:
                    matris[t_str] = {}
                if ist_id not in matris[t_str]:
                    matris[t_str][ist_id] = []
                matris[t_str][ist_id].append(dr_id)
        except:
            continue
    return {"basari": True, "data": matris}

@app.get("/api/onceki-ay-getir")
def get_onceki_ay():
    veri = []
    for o in hastane.onceki_ay_nobetleri:
        dr_isim = next((d["isim"] for d in hastane.doktorlar if d["id"] == o["doktor_id"]), "Bilinmeyen")
        tip = "Son Gün Tuttu" if o["gun_tipi"] == "1" else "Sondan 2. Gün Tuttu"
        veri.append({"id": o["id"], "doktor": dr_isim, "tip": tip})
    return {"basari": True, "data": veri}


# ==========================================
# 6. YAPAY ZEKA NÖBET ALGORİTMASI (OR-TOOLS)
# ==========================================

@app.post("/api/nobet-olustur")
def nobet_olustur(istek: YeniListeIstegi):
    hastane.veritabanindan_yukle(supabase_client) # Algoritma çalışmadan önce en taze veriyi al

    yil = istek.yil
    ay = istek.ay
    num_days = calendar.monthrange(yil, ay)[1]

    aktif_doktorlar = [d for d in hastane.doktorlar if not d.get("muaf_mi", False)]
    doktor_idler = [d["id"] for d in aktif_doktorlar]
    
    if len(doktor_idler) < 2:
        return {"basari": False, "mesaj": "Nöbet yazmak için en az 2 aktif doktor bulunmalıdır."}

    model = cp_model.CpModel()
    nobet = {}
    
    # Her gün için değişkenleri oluştur
    for dr in doktor_idler:
        for gun in range(1, num_days + 1):
            nobet[(dr, gun)] = model.NewBoolVar(f"nobet_dr{dr}_gun{gun}")

    # Kural 1: Her gün TAM OLARAK 2 doktor nöbet tutar
    for gun in range(1, num_days + 1):
        model.AddExactLinearEquation([nobet[(dr, gun)] for dr in doktor_idler], 2)

    # Kural 2: İzinli günler (Kesin Kural)
    for izin in hastane.izinler:
        try:
            iz_tarih = datetime.strptime(izin["tarih"], "%Y-%m-%d")
            if iz_tarih.year == yil and iz_tarih.month == ay and izin["doktor_id"] in doktor_idler:
                model.Add(nobet[(izin["doktor_id"], iz_tarih.day)] == 0)
        except: pass

    # Kural 3: Nöbete Engel Gündüz Mesaisi (Kesin Kural)
    engel_istasyonlar = [i["id"] for i in hastane.istasyonlar if i.get("nobete_engel_mi", False)]
    for gm in hastane.gunduz_mesaileri:
        try:
            gm_tarih = datetime.strptime(gm["tarih"], "%Y-%m-%d")
            if gm_tarih.year == yil and gm_tarih.month == ay and gm["doktor_id"] in doktor_idler:
                if gm["istasyon_id"] in engel_istasyonlar:
                    model.Add(nobet[(gm["doktor_id"], gm_tarih.day)] == 0)
        except: pass

    # Kural 4: 2 Gün Dinlenme Kuralı (Kesin Kural)
    for dr in doktor_idler:
        for gun in range(1, num_days - 1):
            # Nöbet tuttuysa sonraki 2 gün 0 olmalı
            model.AddImplication(nobet[(dr, gun)], nobet[(dr, gun+1)].Not())
            model.AddImplication(nobet[(dr, gun)], nobet[(dr, gun+2)].Not())

    # Kural 5: Önceki Ay Devri
    for oan in hastane.onceki_ay_nobetleri:
        dr_id = oan["doktor_id"]
        if dr_id in doktor_idler:
            if oan["gun_tipi"] == "1": # Önceki ay son gün tutmuş
                model.Add(nobet[(dr_id, 1)] == 0)
                if num_days >= 2: model.Add(nobet[(dr_id, 2)] == 0)
            elif oan["gun_tipi"] == "2": # Önceki ay sondan 2. gün tutmuş
                model.Add(nobet[(dr_id, 1)] == 0)

    # Kural 6: Adil Dağılım Sınırları (Kimse çok fazla veya çok az nöbet tutmasın)
    min_nobet = max(0, (num_days * 2) // len(doktor_idler) - 1)
    max_nobet = (num_days * 2) // len(doktor_idler) + 2
    for dr in doktor_idler:
        dr_nobetleri = [nobet[(dr, gun)] for gun in range(1, num_days + 1)]
        model.Add(sum(dr_nobetleri) >= min_nobet)
        model.Add(sum(dr_nobetleri) <= max_nobet)

    # Kural 7: İstenmeyen Kişiler (Esnek Kural - Cezalandırma Yöntemi)
    ceza_puanlari = []
    for ist in hastane.istenmeyenler:
        dr1 = ist["doktor_id"]
        dr2 = ist["istenmeyen_doktor_id"]
        if dr1 in doktor_idler and dr2 in doktor_idler:
            for gun in range(1, num_days + 1):
                # İkisi aynı gün tutuyorsa ceza yazılır (Sistem tıkanırsa mecbur kalıp yazar, ama kaçınır)
                birlikte = model.NewBoolVar(f"birlikte_{dr1}_{dr2}_gun{gun}")
                model.AddMultiplicationEquality(birlikte, [nobet[(dr1, gun)], nobet[(dr2, gun)]])
                ceza_puanlari.append(birlikte)

    # Amacımız bu ceza puanını sıfıra indirmek / minimize etmek
    model.Minimize(sum(ceza_puanlari))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0 # Çok zorlanırsa en fazla 15 sn düşünsün
    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # Sonucu JSON formatına dönüştür
        liste_json = {}
        for gun in range(1, num_days + 1):
            tarih_str = f"{yil}-{ay:02d}-{gun:02d}"
            gun_index = datetime(yil, ay, gun).weekday()
            nobetciler_idler = [dr for dr in doktor_idler if solver.Value(nobet[(dr, gun)]) == 1]
            nobetciler_isimler = [next(d["isim"] for d in aktif_doktorlar if d["id"] == i) for i in nobetciler_idler]
            
            liste_json[tarih_str] = {
                "gun_adi": GUN_ISIMLERI[gun_index],
                "nobetciler": nobetciler_isimler
            }
        
        uyari_metni = None
        if solver.Value(sum(ceza_puanlari)) > 0:
            uyari_metni = f"Dikkat: Kurallar çok sıkı olduğu için {solver.Value(sum(ceza_puanlari))} adet 'istenmeyen kişi' eşleşmesi yapılmak zorunda kalındı."

        # Eski varsa sil ve yenisini kaydet
        supabase_client.table("aylik_listeler").delete().eq("yil", yil).eq("ay", ay).execute()
        supabase_client.table("aylik_listeler").insert({
            "yil": yil, "ay": ay, "liste_json": liste_json, "uyari_metni": uyari_metni
        }).execute()
        
        return {"basari": True}
    else:
        return {"basari": False, "mesaj": "Kurallar çok sıkı, hiçbir çözüm bulunamadı."}


# ==========================================
# 7. VERİ DEĞİŞTİRME/SİLME UÇ NOKTALARI
# ==========================================

@app.post("/api/liste-sil")
def liste_sil(istek: YeniListeIstegi):
    supabase_client.table("aylik_listeler").delete().eq("yil", istek.yil).eq("ay", istek.ay).execute()
    return {"basari": True}

@app.post("/api/gunduz-mesaisi-kaydet")
def gunduz_mesaisi_kaydet(istek: GunduzMesaisiIstegi):
    supabase_client.table("gunduz_mesaileri").delete().eq("tarih", istek.tarih).eq("istasyon_id", istek.istasyon_id).execute()
    if istek.doktor_idler:
        eklenecekler = [{"tarih": istek.tarih, "istasyon_id": istek.istasyon_id, "doktor_id": d_id} for d_id in istek.doktor_idler]
        supabase_client.table("gunduz_mesaileri").insert(eklenecekler).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.delete("/api/veri-sil/{tablo}/{id}")
def veri_sil(tablo: str, id: int):
    supabase_client.table(tablo).delete().eq("id", id).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.post("/api/izin-ekle")
def api_izin_ekle(istek: IzinIstegi):
    supabase_client.table("izinli_gunler").delete().eq("doktor_id", istek.doktor_id).execute()
    if istek.tarihler:
        supabase_client.table("izinli_gunler").insert([{"doktor_id": istek.doktor_id, "tarih": t} for t in istek.tarihler]).execute()
    hastane.veritabanindan_yukle(supabase_client) # Değişiklik anında RAM'e yansısın
    return {"basari": True, "mesaj": "İzinler başarıyla kaydedildi!"}

@app.post("/api/istenmeyen-guncelle")
def api_istenmeyen_guncelle(istek: GuncelleIstegi):
    supabase_client.table("istenmeyen_kisiler").delete().eq("doktor_id", istek.doktor_id).execute()
    if istek.idler:
        supabase_client.table("istenmeyen_kisiler").insert([{"doktor_id": istek.doktor_id, "istenmeyen_doktor_id": i} for i in istek.idler]).execute()
    hastane.veritabanindan_yukle(supabase_client) # Değişiklik anında RAM'e yansısın
    return {"basari": True, "mesaj": "Kısıtlamalar güncellendi!"}

@app.post("/api/istasyon-ekle")
def istasyon_ekle(istek: YeniIstasyon):
    supabase_client.table("istasyonlar").insert({"isim": istek.isim, "nobete_engel_mi": istek.nobete_engel_mi}).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.post("/api/doktor-ekle")
def doktor_ekle(istek: YeniDoktor):
    supabase_client.table("doktorlar").insert({"isim": istek.isim, "kidem": istek.kidem, "rol": istek.rol, "muaf_mi": istek.muaf_mi}).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.post("/api/onceki-ay-ekle")
def onceki_ay_ekle(istek: OncekiAyDevir):
    supabase_client.table("onceki_ay_nobetleri").delete().eq("doktor_id", istek.doktor_id).execute()
    supabase_client.table("onceki_ay_nobetleri").insert({"doktor_id": istek.doktor_id, "gun_tipi": istek.gun_tipi}).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

# Sistemi çalıştırmak için bu satırı eklemeye gerek yok çünkü uvicorn hastane:app komutu kullanıyoruz.
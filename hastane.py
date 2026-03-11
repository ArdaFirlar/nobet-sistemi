import os
import calendar
import random
from datetime import datetime, date
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from supabase import create_client, Client
from dotenv import load_dotenv
from ortools.sat.python import cp_model

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("HATA: .env dosyasında SUPABASE_URL veya SUPABASE_KEY bulunamadı!")

supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

class TopluGunduzMesaisiIstegi(BaseModel):
    yil: int
    ay: int
    istasyon_id: int
    doktor_idler: List[int]

class YeniIstasyon(BaseModel):
    isim: str
    nobete_engel_mi: bool
    servis_mi: bool
    hafta_sonu_calisir_mi: bool

class YeniDoktor(BaseModel):
    isim: str
    kidem: str
    rol: str
    muaf_mi: bool
    nobet_hedefi: int
    haftasonu_hedefi: int
    kural_tipi: str
    persembe_yasak_mi: bool

class OncekiAyDevir(BaseModel):
    doktor_id: int
    gun_tipi: str

class YeniTatil(BaseModel):
    tarih: str

class HastaneSistemi:
    def __init__(self):
        self.doktorlar = []
        self.istasyonlar = []
        self.izinler = []
        self.istenmeyenler = []
        self.gunduz_mesaileri = []
        self.onceki_ay_nobetleri = []
        self.resmi_tatiller = []

    def veritabanindan_yukle(self, db: Client):
        self.doktorlar = db.table("doktorlar").select("*").execute().data
        self.istasyonlar = db.table("istasyonlar").select("*").execute().data
        self.izinler = db.table("izinli_gunler").select("*").execute().data
        self.istenmeyenler = db.table("istenmeyen_kisiler").select("*").execute().data
        self.gunduz_mesaileri = db.table("gunduz_mesaileri").select("*").execute().data
        self.onceki_ay_nobetleri = db.table("onceki_ay_nobetleri").select("*").execute().data
        
        try:
            self.resmi_tatiller = db.table("resmi_tatiller").select("*").execute().data
        except Exception:
            self.resmi_tatiller = []

hastane = HastaneSistemi()
hastane.veritabanindan_yukle(supabase_client)

GUN_ISIMLERI = {0: "Pzt", 1: "Sal", 2: "Çar", 3: "Per", 4: "Cum", 5: "Cmt", 6: "Paz"}

@app.get("/api/doktorlar")
def get_doktorlar():
    sirali_doktorlar = sorted(hastane.doktorlar, key=lambda x: x["isim"])
    return {"basari": True, "data": sirali_doktorlar}

@app.get("/api/istasyonlar")
def get_istasyonlar():
    sirali_istasyonlar = sorted(hastane.istasyonlar, key=lambda x: x["isim"])
    return {"basari": True, "data": sirali_istasyonlar}

@app.get("/api/resmi-tatiller")
def get_resmi_tatiller():
    return {"basari": True, "data": hastane.resmi_tatiller}

@app.get("/api/doktor-detay/{doktor_id}")
def get_doktor_detay(doktor_id: int):
    izin_sonuc = supabase_client.table("izinli_gunler").select("tarih").eq("doktor_id", doktor_id).execute()
    doktor_izinleri = [iz["tarih"] for iz in izin_sonuc.data] if izin_sonuc.data else []
    return {"basari": True, "izinler": doktor_izinleri}

@app.get("/api/mevcut-liste")
def get_mevcut_liste(yil: int, ay: int):
    sonuc = supabase_client.table("aylik_listeler").select("*").eq("yil", yil).eq("ay", ay).execute()
    if sonuc.data and len(sonuc.data) > 0:
        return {"basari": True, "data": sonuc.data[0]["liste_json"], "uyari": sonuc.data[0].get("uyari_metni")}
    return {"basari": False}

@app.get("/api/gunduz-mesaileri-matris")
def get_matris(yil: int, ay: int):
    matris = {}
    for gm in hastane.gunduz_mesaileri:
        try:
            tarih_obj = datetime.strptime(gm["tarih"].split("T")[0], "%Y-%m-%d")
            if tarih_obj.year == yil and tarih_obj.month == ay:
                if gm["tarih"] not in matris: matris[gm["tarih"]] = {}
                if gm["istasyon_id"] not in matris[gm["tarih"]]: matris[gm["tarih"]][gm["istasyon_id"]] = []
                matris[gm["tarih"]][gm["istasyon_id"]].append(gm["doktor_id"])
        except: continue
    return {"basari": True, "data": matris}

@app.get("/api/onceki-ay-getir")
def get_onceki_ay():
    veri = []
    for o in hastane.onceki_ay_nobetleri:
        dr_isim = next((d["isim"] for d in hastane.doktorlar if d["id"] == o["doktor_id"]), "Bilinmeyen")
        tip_metni = "Son Gün Tuttu" if str(o["gun_tipi"]) == "1" else "Sondan 2. Gün Tuttu"
        veri.append({"id": o["id"], "doktor": dr_isim, "tip": tip_metni})
    return {"basari": True, "data": veri}

@app.post("/api/nobet-olustur")
def nobet_olustur(istek: YeniListeIstegi):
    hastane.veritabanindan_yukle(supabase_client)

    yil = istek.yil
    ay = istek.ay
    num_days = int(calendar.monthrange(yil, ay)[1])

    aktif_doktorlar = [d for d in hastane.doktorlar if not d.get("muaf_mi", False)]
    doktor_idler = [d["id"] for d in aktif_doktorlar]
    
    if len(doktor_idler) < 3:
        return {"basari": False, "mesaj": "Hafta sonu nöbeti yazmak için en az 3 aktif doktor bulunmalıdır."}

    asistan_idler = [d["id"] for d in aktif_doktorlar if d.get("kidem") == "ASISTAN"]

    haftasonu_gunler = [g for g in range(1, num_days + 1) if datetime(yil, ay, g).weekday() >= 5]
    resmi_tatil_gunleri = []
    
    for tatil in hastane.resmi_tatiller:
        try:
            tarih_str = str(tatil["tarih"]).split("T")[0]
            t_y, t_a, t_g = map(int, tarih_str.split("-"))
            if t_y == yil and t_a == ay:
                if t_g not in resmi_tatil_gunleri:
                    resmi_tatil_gunleri.append(t_g)
                if t_g not in haftasonu_gunler:
                    haftasonu_gunler.append(t_g)
        except Exception: pass
    
    persembe_gunler = [g for g in range(1, num_days + 1) if datetime(yil, ay, g).weekday() == 3]

    model = cp_model.CpModel()
    nobet = {}
    
    # CEZALARI İKİYE AYIRIYORUZ: Optimizasyon (Hafif) ve Taviz (Ağır)
    taviz_cezalari = []
    optimizasyon_cezalari = []
    
    for dr in doktor_idler:
        for gun in range(1, num_days + 1):
            nobet[(dr, gun)] = model.NewBoolVar(f"nobet_dr{dr}_gun{gun}")

    # =========================================================
    # GÜNCELLENDİ: RESMİ TATİLLER ESNEK KİŞİ SAYISI (2 veya 3)
    # =========================================================
    eksik_tatil_varlari = {}
    for gun in range(1, num_days + 1):
        toplam_dr = sum(nobet[(dr, gun)] for dr in doktor_idler)
        if gun in resmi_tatil_gunleri:
            model.Add(toplam_dr >= 2)
            model.Add(toplam_dr <= 3)
            eksik = model.NewIntVar(0, 1, f"eksik_tatil_g{gun}")
            model.Add(toplam_dr + eksik == 3)
            taviz_cezalari.append(eksik * 3000)
            eksik_tatil_varlari[gun] = eksik
        elif gun in haftasonu_gunler:
            model.Add(toplam_dr == 3)
        else:
            model.Add(toplam_dr == 2)

    for izin in hastane.izinler:
        try:
            tarih_str = str(izin["tarih"]).split("T")[0]
            iz_y, iz_a, iz_g = map(int, tarih_str.split("-"))
            d_id = int(izin["doktor_id"])
            if iz_y == yil and iz_a == ay and d_id in doktor_idler:
                model.Add(nobet[(d_id, iz_g)] == 0)
        except Exception: pass

    engel_istasyonlar = []
    for i in hastane.istasyonlar:
        val = i.get("nobete_engel_mi")
        if val is True or str(val).lower() == "true" or val == 1 or str(val) == "1":
            engel_istasyonlar.append(int(i["id"]))
            
    for gm in hastane.gunduz_mesaileri:
        try:
            tarih_str = str(gm["tarih"]).split("T")[0]
            gm_y, gm_a, gm_g = map(int, tarih_str.split("-"))
            d_id = int(gm["doktor_id"])
            ist_id = int(gm["istasyon_id"])
            if gm_y == yil and gm_a == ay and d_id in doktor_idler:
                if ist_id in engel_istasyonlar:
                    model.Add(nobet[(d_id, gm_g)] == 0)
        except Exception: pass

    servis_istasyon_idler = []
    for i in hastane.istasyonlar:
        val = i.get("servis_mi")
        if val is True or str(val).lower() == "true" or val == 1 or str(val) == "1":
            servis_istasyon_idler.append(int(i["id"]))

    servis_gunluk_calisanlar = {}
    for gm in hastane.gunduz_mesaileri:
        try:
            gm_ist_id = int(gm["istasyon_id"])
            if gm_ist_id in servis_istasyon_idler:
                tarih_str = str(gm["tarih"]).split("T")[0] 
                yil_gm, ay_gm, gun_gm = map(int, tarih_str.split("-"))
                if yil_gm == yil and ay_gm == ay:
                    if gun_gm not in servis_gunluk_calisanlar:
                        servis_gunluk_calisanlar[gun_gm] = set()
                    dr_id = int(gm["doktor_id"])
                    if dr_id in doktor_idler:
                        servis_gunluk_calisanlar[gun_gm].add(dr_id)
        except Exception: pass

    for gun in range(1, num_days): 
        ertesi_gun = gun + 1
        if ertesi_gun in servis_gunluk_calisanlar:
            yarin_servistekiler = list(servis_gunluk_calisanlar[ertesi_gun])
            if len(yarin_servistekiler) > 1:
                gece_kalanlar = sum(nobet[(dr, gun)] for dr in yarin_servistekiler)
                fazla = model.NewIntVar(0, 10, f"fazla_ertesi_servis_g{gun}")
                model.Add(fazla >= gece_kalanlar - 1)
                taviz_cezalari.append(fazla * 2000)

    for gun_gm, dr_set in servis_gunluk_calisanlar.items():
        if len(dr_set) > 1:
            dr_list = list(dr_set)
            gece_kalanlar = sum(nobet[(dr, gun_gm)] for dr in dr_list)
            fazla = model.NewIntVar(0, 10, f"fazla_ayni_servis_g{gun_gm}")
            model.Add(fazla >= gece_kalanlar - 1)
            taviz_cezalari.append(fazla * 2000)

    for dr in doktor_idler:
        for gun in range(1, num_days + 1):
            if gun + 1 <= num_days:
                model.Add(nobet[(dr, gun)] + nobet[(dr, gun+1)] <= 1)
            if gun + 2 <= num_days:
                model.Add(nobet[(dr, gun)] + nobet[(dr, gun+2)] <= 1)

    for oan in hastane.onceki_ay_nobetleri:
        dr_id = oan["doktor_id"]
        if dr_id in doktor_idler:
            if str(oan["gun_tipi"]) == "1":
                model.Add(nobet[(dr_id, 1)] == 0)
                if num_days >= 2: model.Add(nobet[(dr_id, 2)] == 0)
            elif str(oan["gun_tipi"]) == "2":
                model.Add(nobet[(dr_id, 1)] == 0)

    esnek_dr_yukleri = []
    dr_ek_kotalari = {} # Arayüzde kimin kotasının aşıldığını bilmek için
    
    for dr in doktor_idler:
        dr_data = next((d for d in aktif_doktorlar if d["id"] == dr), {})
        n_hedef = dr_data.get("nobet_hedefi") or 4
        h_hedef = dr_data.get("haftasonu_hedefi") or 1
        k_tipi = dr_data.get("kural_tipi") or "MAX"
        p_yasak = dr_data.get("persembe_yasak_mi", False)

        dr_toplam_nobet = sum(nobet[(dr, gun)] for gun in range(1, num_days + 1))
        dr_haftasonu_nobet = sum(nobet[(dr, gun)] for gun in haftasonu_gunler)
        
        # =========================================================
        # GÜNCELLENDİ: EĞER PERŞEMBE TATİLSE YASAK İPTAL!
        # =========================================================
        if p_yasak:
            for gun in persembe_gunler:
                if gun not in resmi_tatil_gunleri: # 23 Nisan vb tatillerde herkes tutabilir
                    model.Add(nobet[(dr, gun)] == 0)
                
        # =========================================================
        # GÜNCELLENDİ: KOTA ESNEMESİ (Anti-Kilit Kalkanı)
        # =========================================================
        ek_toplam = model.NewIntVar(0, 3, f"ek_toplam_{dr}")
        ek_hs = model.NewIntVar(0, 3, f"ek_hs_{dr}")
        taviz_cezalari.append(ek_toplam * 4000)
        taviz_cezalari.append(ek_hs * 4000)
        dr_ek_kotalari[dr] = (ek_toplam, ek_hs)

        if k_tipi == "TAM":
            model.Add(dr_toplam_nobet == n_hedef + ek_toplam)
            model.Add(dr_haftasonu_nobet == h_hedef + ek_hs)
        elif k_tipi == "MAX":
            model.Add(dr_toplam_nobet <= n_hedef + ek_toplam)
            model.Add(dr_haftasonu_nobet <= h_hedef + ek_hs)
            
            dr_yuk = model.NewIntVar(0, 50, f"yuk_dr_{dr}")
            model.Add(dr_yuk == dr_toplam_nobet + dr_haftasonu_nobet)
            esnek_dr_yukleri.append(dr_yuk)
            
            for gun in haftasonu_gunler:
                optimizasyon_cezalari.append(nobet[(dr, gun)] * 50)

    for dr in asistan_idler:
        # Perşembe adaleti (Tatil olmayan perşembeler için)
        saf_persembeler = [g for g in persembe_gunler if g not in resmi_tatil_gunleri]
        dr_persembe_toplam = sum(nobet[(dr, gun)] for gun in saf_persembeler)
        
        for gun in saf_persembeler:
            optimizasyon_cezalari.append(nobet[(dr, gun)] * 10)
            
        fazla_persembe = model.NewIntVar(0, 5, f"fazla_persembe_{dr}")
        model.Add(fazla_persembe >= dr_persembe_toplam - 1)
        optimizasyon_cezalari.append(fazla_persembe * 500)

    for ist in hastane.istenmeyenler:
        dr1 = ist["doktor_id"]
        dr2 = ist["istenmeyen_doktor_id"]
        if dr1 in doktor_idler and dr2 in doktor_idler:
            for gun in range(1, num_days + 1):
                birlikte = model.NewBoolVar(f"birlikte_{dr1}_{dr2}_gun{gun}")
                model.AddMultiplicationEquality(birlikte, [nobet[(dr1, gun)], nobet[(dr2, gun)]])
                taviz_cezalari.append(birlikte * 5000)

    if len(esnek_dr_yukleri) > 1:
        max_yuk = model.NewIntVar(0, 50, "max_yuk")
        min_yuk = model.NewIntVar(0, 50, "min_yuk")
        model.AddMaxEquality(max_yuk, esnek_dr_yukleri)
        model.AddMinEquality(min_yuk, esnek_dr_yukleri)
        fark = model.NewIntVar(0, 50, "yuk_farki")
        model.Add(fark == max_yuk - min_yuk)
        optimizasyon_cezalari.append(fark * 1000)

    model.Minimize(sum(taviz_cezalari) + sum(optimizasyon_cezalari))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 15.0
    solver.parameters.randomize_search = True
    solver.parameters.random_seed = random.randint(1, 10000)

    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        liste_json = {}
        for gun in range(1, num_days + 1):
            tarih_str = f"{yil}-{ay:02d}-{gun:02d}"
            gun_index = datetime(yil, ay, gun).weekday()
            nobetciler_idler_gun = [dr for dr in doktor_idler if solver.Value(nobet[(dr, gun)]) == 1]
            
            detayli_nobetciler = []
            for d_id in nobetciler_idler_gun:
                isim = next(d["isim"] for d in aktif_doktorlar if d["id"] == d_id)
                riskli = False
                sebep = []
                
                if gun in servis_gunluk_calisanlar and d_id in servis_gunluk_calisanlar[gun]:
                    ayni_gun_sayisi = sum(1 for x in nobetciler_idler_gun if x in servis_gunluk_calisanlar[gun])
                    if ayni_gun_sayisi > 1:
                        riskli = True
                        sebep.append("Aynı Gün Servis Çakışması")
                        
                ertesi_gun = gun + 1
                if ertesi_gun in servis_gunluk_calisanlar and d_id in servis_gunluk_calisanlar[ertesi_gun]:
                    ertesi_gun_sayisi = sum(1 for x in nobetciler_idler_gun if x in servis_gunluk_calisanlar[ertesi_gun])
                    if ertesi_gun_sayisi > 1:
                        riskli = True
                        sebep.append("Ertesi Gün Servis Çakışması")
                
                # Yeni: Kotası aşılan doktoru yakala
                ek_top, ek_hs = dr_ek_kotalari[d_id]
                if solver.Value(ek_top) > 0 or solver.Value(ek_hs) > 0:
                    riskli = True
                    sebep.append("Aylık Kotası Dolduğu Halde Mecburen Yazıldı")
                        
                detayli_nobetciler.append({
                    "isim": isim,
                    "riskli": riskli,
                    "sebep": " | ".join(sebep) if sebep else ""
                })
            
            eksik_kisi_var = False
            if gun in eksik_tatil_varlari and solver.Value(eksik_tatil_varlari[gun]) > 0:
                eksik_kisi_var = True

            liste_json[tarih_str] = {
                "gun_adi": GUN_ISIMLERI[gun_index],
                "nobetciler": [d["isim"] for d in detayli_nobetciler],
                "nobetciler_detay": detayli_nobetciler,
                "eksik_kisi": eksik_kisi_var
            }
        
        # SADECE GERÇEK TAVİZ VERİLDİYSE YUKARIYA UYARI MESAJI GİDER
        uyari_metni = None
        toplam_taviz_cezasi = solver.Value(sum(taviz_cezalari)) if len(taviz_cezalari) > 0 else 0
        if toplam_taviz_cezasi > 0:
            uyari_metni = "Algoritma doktor yetersizliği veya kuralların aşırı sıkışması nedeniyle bazı tavizler vermek zorunda kaldı!"

        supabase_client.table("aylik_listeler").delete().eq("yil", yil).eq("ay", ay).execute()
        supabase_client.table("aylik_listeler").insert({
            "yil": yil, "ay": ay, "liste_json": liste_json, "uyari_metni": uyari_metni
        }).execute()
        
        return {"basari": True}
    else:
        hata_nedenleri = []
        try:
            izinler_dict = {}
            for iz in hastane.izinler:
                try:
                    t = str(iz["tarih"]).split("T")[0]
                    y, a, g = map(int, t.split("-"))
                    if y == yil and a == ay:
                        izinler_dict.setdefault(g, set()).add(int(iz["doktor_id"]))
                except: pass
                
            engelliler_dict = {}
            engel_ist_idler = [int(i["id"]) for i in hastane.istasyonlar if i.get("nobete_engel_mi")]
            for gm in hastane.gunduz_mesaileri:
                try:
                    t = str(gm["tarih"]).split("T")[0]
                    y, a, g = map(int, t.split("-"))
                    if y == yil and a == ay:
                        d_id = int(gm["doktor_id"])
                        ist_id = int(gm["istasyon_id"])
                        if ist_id in engel_ist_idler:
                            engelliler_dict.setdefault(g, set()).add(d_id)
                except: pass

            toplam_gerekli_nobet = sum(3 if (g in haftasonu_gunler or g in resmi_tatil_gunleri) else 2 for g in range(1, num_days + 1))
            toplam_dr_kapasitesi = sum(int(dr.get("nobet_hedefi", 4)) for dr in aktif_doktorlar)
            
            if toplam_dr_kapasitesi < toplam_gerekli_nobet:
                hata_nedenleri.append(f"Aylık kapasite kilitlenmesi! Toplam nöbet {toplam_gerekli_nobet} ancak kotalar toplamı {toplam_dr_kapasitesi}.")

            yasakli_persembeler = {int(d["id"]) for d in aktif_doktorlar if d.get("persembe_yasak_mi")}

            for gun in range(1, num_days + 1):
                gerekli = 3 if (gun in haftasonu_gunler or gun in resmi_tatil_gunleri) else 2
                musaitler = set(doktor_idler)
                musaitler -= izinler_dict.get(gun, set())
                musaitler -= engelliler_dict.get(gun, set())
                if gun in persembe_gunler and gun not in resmi_tatil_gunleri:
                    musaitler -= yasakli_persembeler
                    
                if len(musaitler) < gerekli:
                    hata_nedenleri.append(f"Ayın {gun}. Günü: İzinler ve yasaklar yüzünden yeterli kişi yok (Gereken: {gerekli}, Müsait: {len(musaitler)}).")
                    
            if not hata_nedenleri:
                hata_nedenleri.append("Özel bir günde sorun yok. Sistem '2 Gün Dinlenme' kuralı veya matematiksel döngü nedeniyle kilitlendi.")

            mesaj = "❌ Kurallar Çok Sıkı!\nAlgoritma şu sebeplerden dolayı listeyi oluşturamadı:\n\n" + "\n".join(f"👉 {h}" for h in hata_nedenleri[:5])
            if len(hata_nedenleri) > 5:
                mesaj += f"\n\n... ve {len(hata_nedenleri)-5} benzer sorun daha tespit edildi."
                
        except Exception as e:
            mesaj = f"❌ Kurallar çok sıkı, hiçbir çözüm bulunamadı. (Teşhis hatası: {str(e)})"
            
        return {"basari": False, "mesaj": mesaj}

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

@app.post("/api/gunduz-mesaisi-toplu-kaydet")
def gunduz_mesaisi_toplu_kaydet(istek: TopluGunduzMesaisiIstegi):
    num_days = calendar.monthrange(istek.yil, istek.ay)[1]
    istasyon = next((i for i in hastane.istasyonlar if i["id"] == istek.istasyon_id), None)
    haftasonu_calisir = istasyon.get("hafta_sonu_calisir_mi", False) if istasyon else False

    tum_tarihler = [f"{istek.yil}-{istek.ay:02d}-{g:02d}" for g in range(1, num_days + 1)]
    for t in tum_tarihler:
        supabase_client.table("gunduz_mesaileri").delete().eq("tarih", t).eq("istasyon_id", istek.istasyon_id).execute()

    if istek.doktor_idler:
        eklenecekler = []
        for g in range(1, num_days + 1):
            gun_index = datetime(istek.yil, istek.ay, g).weekday()
            is_weekend = gun_index >= 5
            if is_weekend and not haftasonu_calisir: continue
            t = f"{istek.yil}-{istek.ay:02d}-{g:02d}"
            for d_id in istek.doktor_idler:
                eklenecekler.append({"tarih": t, "istasyon_id": istek.istasyon_id, "doktor_id": d_id})
        if eklenecekler:
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
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True, "mesaj": "İzinler kaydedildi!"}

@app.post("/api/resmi-tatil-ekle")
def resmi_tatil_ekle(istek: YeniTatil):
    supabase_client.table("resmi_tatiller").insert({"tarih": istek.tarih}).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.post("/api/istasyon-ekle")
def istasyon_ekle(istek: YeniIstasyon):
    supabase_client.table("istasyonlar").insert({
        "isim": istek.isim, "nobete_engel_mi": istek.nobete_engel_mi, 
        "servis_mi": istek.servis_mi, "hafta_sonu_calisir_mi": istek.hafta_sonu_calisir_mi
    }).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.put("/api/istasyon-guncelle/{id}")
def istasyon_guncelle(id: int, istek: YeniIstasyon):
    supabase_client.table("istasyonlar").update({
        "isim": istek.isim, "nobete_engel_mi": istek.nobete_engel_mi, 
        "servis_mi": istek.servis_mi, "hafta_sonu_calisir_mi": istek.hafta_sonu_calisir_mi
    }).eq("id", id).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.post("/api/doktor-ekle")
def doktor_ekle(istek: YeniDoktor):
    supabase_client.table("doktorlar").insert({
        "isim": istek.isim, "kidem": istek.kidem, "rol": istek.rol, "muaf_mi": istek.muaf_mi,
        "nobet_hedefi": istek.nobet_hedefi, "haftasonu_hedefi": istek.haftasonu_hedefi,
        "kural_tipi": istek.kural_tipi, "persembe_yasak_mi": istek.persembe_yasak_mi
    }).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.put("/api/doktor-guncelle/{id}")
def doktor_guncelle(id: int, istek: YeniDoktor):
    supabase_client.table("doktorlar").update({
        "isim": istek.isim, "kidem": istek.kidem, "rol": istek.rol, "muaf_mi": istek.muaf_mi,
        "nobet_hedefi": istek.nobet_hedefi, "haftasonu_hedefi": istek.haftasonu_hedefi,
        "kural_tipi": istek.kural_tipi, "persembe_yasak_mi": istek.persembe_yasak_mi
    }).eq("id", id).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}

@app.post("/api/onceki-ay-ekle")
def onceki_ay_ekle(istek: OncekiAyDevir):
    supabase_client.table("onceki_ay_nobetleri").delete().eq("doktor_id", istek.doktor_id).execute()
    supabase_client.table("onceki_ay_nobetleri").insert({"doktor_id": istek.doktor_id, "gun_tipi": istek.gun_tipi}).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True}
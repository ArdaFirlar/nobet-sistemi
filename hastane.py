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

@app.get("/api/doktor-detay/{doktor_id}")
def get_doktor_detay(doktor_id: int):
    izin_sonuc = supabase_client.table("izinli_gunler").select("tarih").eq("doktor_id", doktor_id).execute()
    istenmeyen_sonuc = supabase_client.table("istenmeyen_kisiler").select("istenmeyen_doktor_id").eq("doktor_id", doktor_id).execute()
    
    doktor_izinleri = [iz["tarih"] for iz in izin_sonuc.data] if izin_sonuc.data else []
    doktor_istenmeyenler = [ist["istenmeyen_doktor_id"] for ist in istenmeyen_sonuc.data] if istenmeyen_sonuc.data else []
    
    return {"basari": True, "izinler": doktor_izinleri, "istenmeyenler": doktor_istenmeyenler}

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
            tarih_obj = datetime.strptime(gm["tarih"], "%Y-%m-%d")
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
    persembe_gunler = [g for g in range(1, num_days + 1) if datetime(yil, ay, g).weekday() == 3]

    model = cp_model.CpModel()
    nobet = {}
    
    for dr in doktor_idler:
        for gun in range(1, num_days + 1):
            nobet[(dr, gun)] = model.NewBoolVar(f"nobet_dr{dr}_gun{gun}")

    for gun in range(1, num_days + 1):
        if gun in haftasonu_gunler:
            model.Add(sum(nobet[(dr, gun)] for dr in doktor_idler) == 3)
        else:
            model.Add(sum(nobet[(dr, gun)] for dr in doktor_idler) == 2)

    for izin in hastane.izinler:
        try:
            iz_tarih = datetime.strptime(izin["tarih"], "%Y-%m-%d")
            if iz_tarih.year == yil and iz_tarih.month == ay and izin["doktor_id"] in doktor_idler:
                model.Add(nobet[(izin["doktor_id"], iz_tarih.day)] == 0)
        except: pass

    engel_istasyonlar = [i["id"] for i in hastane.istasyonlar if i.get("nobete_engel_mi", False)]
    for gm in hastane.gunduz_mesaileri:
        try:
            gm_tarih = datetime.strptime(gm["tarih"], "%Y-%m-%d")
            if gm_tarih.year == yil and gm_tarih.month == ay and gm["doktor_id"] in doktor_idler:
                if gm["istasyon_id"] in engel_istasyonlar:
                    model.Add(nobet[(gm["doktor_id"], gm_tarih.day)] == 0)
        except: pass

    gunluk_mesaiciler = {}
    for gm in hastane.gunduz_mesaileri:
        try:
            tarih_str = str(gm["tarih"]).split("T")[0] 
            yil_gm, ay_gm, gun_gm = map(int, tarih_str.split("-"))
            if yil_gm == yil and ay_gm == ay:
                if gun_gm not in gunluk_mesaiciler:
                    gunluk_mesaiciler[gun_gm] = set()
                dr_id = int(gm["doktor_id"])
                if dr_id in doktor_idler:
                    gunluk_mesaiciler[gun_gm].add(dr_id)
        except Exception: pass

    for gun in range(1, num_days): 
        ertesi_gun = gun + 1
        if ertesi_gun in gunluk_mesaiciler:
            ertesi_gunun_doktorlari = list(gunluk_mesaiciler[ertesi_gun])
            if len(ertesi_gunun_doktorlari) > 1:
                model.Add(sum(nobet[(dr, gun)] for dr in ertesi_gunun_doktorlari) <= 1)

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
            
    for gun_gm, dr_set in servis_gunluk_calisanlar.items():
        if len(dr_set) > 1:
            dr_list = list(dr_set)
            model.Add(sum(nobet[(dr, gun_gm)] for dr in dr_list) <= 1)

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
    ceza_puanlari = []
    
    for dr in doktor_idler:
        dr_data = next((d for d in aktif_doktorlar if d["id"] == dr), {})
        
        n_hedef = dr_data.get("nobet_hedefi") or 4
        h_hedef = dr_data.get("haftasonu_hedefi") or 1
        k_tipi = dr_data.get("kural_tipi") or "MAX"
        p_yasak = dr_data.get("persembe_yasak_mi", False)

        dr_toplam_nobet = sum(nobet[(dr, gun)] for gun in range(1, num_days + 1))
        dr_haftasonu_nobet = sum(nobet[(dr, gun)] for gun in haftasonu_gunler)
        
        if p_yasak:
            for gun in persembe_gunler:
                model.Add(nobet[(dr, gun)] == 0)
                
        if k_tipi == "TAM":
            model.Add(dr_toplam_nobet == n_hedef)
            model.Add(dr_haftasonu_nobet == h_hedef)
            
        elif k_tipi == "MAX":
            model.Add(dr_toplam_nobet <= n_hedef)
            model.Add(dr_haftasonu_nobet <= h_hedef)
            
            dr_yuk = model.NewIntVar(0, 50, f"yuk_dr_{dr}")
            model.Add(dr_yuk == dr_toplam_nobet + dr_haftasonu_nobet)
            esnek_dr_yukleri.append(dr_yuk)
            
            for gun in haftasonu_gunler:
                ceza_puanlari.append(nobet[(dr, gun)] * 50)

    for dr in asistan_idler:
        dr_persembe_toplam = sum(nobet[(dr, gun)] for gun in persembe_gunler)
        for gun in persembe_gunler:
            ceza_puanlari.append(nobet[(dr, gun)] * 10)
        fazla_persembe = model.NewIntVar(0, 5, f"fazla_persembe_{dr}")
        model.Add(fazla_persembe >= dr_persembe_toplam - 1)
        ceza_puanlari.append(fazla_persembe * 500)

    for ist in hastane.istenmeyenler:
        dr1 = ist["doktor_id"]
        dr2 = ist["istenmeyen_doktor_id"]
        if dr1 in doktor_idler and dr2 in doktor_idler:
            for gun in range(1, num_days + 1):
                birlikte = model.NewBoolVar(f"birlikte_{dr1}_{dr2}_gun{gun}")
                model.AddMultiplicationEquality(birlikte, [nobet[(dr1, gun)], nobet[(dr2, gun)]])
                ceza_puanlari.append(birlikte * 100)

    if len(esnek_dr_yukleri) > 1:
        max_yuk = model.NewIntVar(0, 50, "max_yuk")
        min_yuk = model.NewIntVar(0, 50, "min_yuk")
        model.AddMaxEquality(max_yuk, esnek_dr_yukleri)
        model.AddMinEquality(min_yuk, esnek_dr_yukleri)
        fark = model.NewIntVar(0, 50, "yuk_farki")
        model.Add(fark == max_yuk - min_yuk)
        ceza_puanlari.append(fark * 1000)

    if len(ceza_puanlari) > 0:
        model.Minimize(sum(ceza_puanlari))

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
            nobetciler_idler = [dr for dr in doktor_idler if solver.Value(nobet[(dr, gun)]) == 1]
            nobetciler_isimler = [next(d["isim"] for d in aktif_doktorlar if d["id"] == i) for i in nobetciler_idler]
            
            liste_json[tarih_str] = {
                "gun_adi": GUN_ISIMLERI[gun_index],
                "nobetciler": nobetciler_isimler
            }
        
        uyari_metni = None
        toplam_ceza = solver.Value(sum(ceza_puanlari)) if len(ceza_puanlari) > 0 else 0
        if toplam_ceza > 0:
            uyari_metni = f"Dikkat: Kurallar sıkı olduğu için algoritma bazı tavizler verdi. (Ceza Skoru: {toplam_ceza})"

        supabase_client.table("aylik_listeler").delete().eq("yil", yil).eq("ay", ay).execute()
        supabase_client.table("aylik_listeler").insert({
            "yil": yil, "ay": ay, "liste_json": liste_json, "uyari_metni": uyari_metni
        }).execute()
        
        return {"basari": True}
    else:
        # =========================================================
        # YAPAY ZEKA HATA TEŞHİS MOTORU (DEDEKİF MODU)
        # =========================================================
        hata_nedenleri = []
        
        izinler_dict = {}
        for iz in hastane.izinler:
            try:
                t = datetime.strptime(iz["tarih"], "%Y-%m-%d")
                if t.year == yil and t.month == ay:
                    izinler_dict.setdefault(t.day, set()).add(int(iz["doktor_id"]))
            except: pass
            
        engelliler_dict = {}
        yarin_calisan_dict = {}
        engel_ist_idler = [int(i["id"]) for i in hastane.istasyonlar if i.get("nobete_engel_mi")]
        
        for gm in hastane.gunduz_mesaileri:
            try:
                t = str(gm["tarih"]).split("T")[0]
                y, a, g = map(int, t.split("-"))
                if y == yil and a == ay:
                    d_id = int(gm["doktor_id"])
                    ist_id = int(gm["istasyon_id"])
                    yarin_calisan_dict.setdefault(g, set()).add(d_id)
                    if ist_id in engel_ist_idler:
                        engelliler_dict.setdefault(g, set()).add(d_id)
            except: pass

        toplam_gerekli_nobet = sum(3 if g in haftasonu_gunler else 2 for g in range(1, num_days + 1))
        toplam_dr_kapasitesi = sum(int(dr.get("nobet_hedefi", 4)) for dr in aktif_doktorlar)
        
        if toplam_dr_kapasitesi < toplam_gerekli_nobet:
            hata_nedenleri.append(f"Aylık toplam kapasite yetersiz! Bu ay {toplam_gerekli_nobet} boş nöbet var ama doktorların hedefleri toplamı {toplam_dr_kapasitesi}.")

        yasakli_persembeler = {int(d["id"]) for d in aktif_doktorlar if d.get("persembe_yasak_mi")}

        for gun in range(1, num_days + 1):
            gerekli = 3 if gun in haftasonu_gunler else 2
            musaitler = set(doktor_idler)
            
            musaitler -= izinler_dict.get(gun, set())
            musaitler -= engelliler_dict.get(gun, set())
            
            if gun in persembe_gunler:
                musaitler -= yasakli_persembeler
                
            if len(musaitler) < gerekli:
                hata_nedenleri.append(f"Ayın {gun}. Günü: İzinler ve engel istasyonlar yüzünden {gerekli} kişi çıkmıyor (Sadece {len(musaitler)} kişi müsait).")
                continue
                
            ertesi_gun = gun + 1
            if ertesi_gun <= num_days:
                yarin_calisanlar = yarin_calisan_dict.get(ertesi_gun, set())
                sadece_bugun = musaitler - yarin_calisanlar
                kesisim = musaitler.intersection(yarin_calisanlar)
                
                max_yazilabilen = len(sadece_bugun) + (1 if kesisim else 0)
                if max_yazilabilen < gerekli:
                    hata_nedenleri.append(f"Ayın {gun}. Günü: Ertesi gün mesaisi olanları koruma kuralı yüzünden tıkandı (Ertesi gün çok kişi mesaide).")
                    
        if not hata_nedenleri:
            hata_nedenleri.append("Genel Kilitlenme: Özel bir gün değil ancak '2 Gün Dinlenme' kuralı, kotalar ve servis kısıtlamaları üst üste binip matematiksel olarak çıkmaza girdi.")

        mesaj = "❌ Kurallar Çok Sıkı!\nAlgoritma şu sebeplerden dolayı tıkandı:\n\n" + "\n".join(f"👉 {h}" for h in hata_nedenleri[:5])
        if len(hata_nedenleri) > 5:
            mesaj += f"\n\n... ve {len(hata_nedenleri)-5} sorunlu gün daha tespit edildi."
            
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
    haftasonu_calisir = istasyon.get("haft_sonu_calisir_mi", False) if istasyon else False

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

@app.post("/api/istenmeyen-guncelle")
def api_istenmeyen_guncelle(istek: GuncelleIstegi):
    supabase_client.table("istenmeyen_kisiler").delete().eq("doktor_id", istek.doktor_id).execute()
    if istek.idler:
        supabase_client.table("istenmeyen_kisiler").insert([{"doktor_id": istek.doktor_id, "istenmeyen_doktor_id": i} for i in istek.idler]).execute()
    hastane.veritabanindan_yukle(supabase_client)
    return {"basari": True, "mesaj": "Kısıtlamalar güncellendi!"}

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
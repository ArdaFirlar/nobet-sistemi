import random
import math
from enum import Enum
from datetime import date, timedelta
from typing import Any, Dict
from pydantic import BaseModel
from ortools.sat.python import cp_model
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
import os
from dotenv import load_dotenv
load_dotenv()
# ==========================================
# 1. KULLANICI ROLLERİ VE SINIFLAR
# ==========================================
class Kidem(Enum):
    EN_COMEZ = 1
    COMEZ = 2
    ASISTAN = 3

class Rol(Enum):
    STANDART = "Standart"
    ADMIN = "Admin"

class MesaiIstasyonu:
    def __init__(self, id: int, isim: str, nobete_engel_mi: bool = False):
        self.id = id
        self.isim = isim
        self.nobete_engel_mi = nobete_engel_mi

class Doktor:
    def __init__(self, doktor_id: int, isim: str, kidem: Kidem, rol: Rol = Rol.STANDART, muaf_mi: bool = False):
        self.id = doktor_id
        self.isim = isim
        self.kidem = kidem
        self.rol = rol
        self.muaf_mi = muaf_mi 
        
        if kidem == Kidem.EN_COMEZ: self.aylik_nobet_hedefi = 6
        elif kidem == Kidem.COMEZ: self.aylik_nobet_hedefi = 5
        else: self.aylik_nobet_hedefi = 4
        
        self.izinli_gunler = set() 
        self.istenmeyen_kisiler = set()
        self.gunduz_mesaileri = {} 
        self.yasakli_gunler = set()
        
        if self.kidem in [Kidem.EN_COMEZ, Kidem.COMEZ]:
            self.yasakli_gunler.add(3)

    def nobet_tutabilir_mi(self, kontrol_tarihi: date) -> bool:
        if self.muaf_mi: return False
        if kontrol_tarihi in self.izinli_gunler: return False
        if kontrol_tarihi.weekday() in self.yasakli_gunler: return False
        return True 

    def istenmeyen_kisi_ekle(self, baska_doktor_id: int):
        self.istenmeyen_kisiler.add(baska_doktor_id)

# ==========================================
# 2. HASTANE SİSTEMİ VE ALGORİTMA
# ==========================================
class HastaneSistemi:
    def __init__(self):
        self.doktorlar = {}
        self.istasyonlar = {}
        self.onceki_ay_kayitlari = []

    def veritabanindan_yukle(self, supabase: Client):
        self.doktorlar.clear()
        self.istasyonlar.clear()
        
        ist_res = supabase.table("istasyonlar").select("*").execute()
        for ist in ist_res.data: # type: ignore
            self.istasyonlar[int(ist['id'])] = MesaiIstasyonu(int(ist['id']), str(ist['isim']), bool(ist.get('nobete_engel_mi', False)))

        dr_res = supabase.table("doktorlar").select("*").execute()
        for dr in dr_res.data: # type: ignore
            kidem = Kidem[str(dr.get('kidem', 'COMEZ'))]
            rol = Rol(str(dr['rol'])) if dr.get('rol') else Rol.STANDART
            yeni_dr = Doktor(int(dr['id']), str(dr['isim']), kidem, rol, bool(dr.get('muaf_mi', False)))
            self.doktorlar[yeni_dr.id] = yeni_dr

        izin_res = supabase.table("izinli_gunler").select("*").execute()
        for izin in izin_res.data: # type: ignore
            if int(izin['doktor_id']) in self.doktorlar:
                self.doktorlar[int(izin['doktor_id'])].izinli_gunler.add(date.fromisoformat(izin['tarih']))

        ist_kisi_res = supabase.table("istenmeyen_kisiler").select("*").execute()
        for k in ist_kisi_res.data: # type: ignore
            if int(k['doktor_id']) in self.doktorlar:
                self.doktorlar[int(k['doktor_id'])].istenmeyen_kisi_ekle(int(k['istenmeyen_doktor_id']))

        gm_res = supabase.table("gunduz_mesaileri").select("*").execute()
        for gm in gm_res.data: # type: ignore
            dr_id, ist_id, t_str = int(gm['doktor_id']), int(gm['istasyon_id']), gm['tarih']
            if dr_id in self.doktorlar and ist_id in self.istasyonlar:
                self.doktorlar[dr_id].gunduz_mesaileri[date.fromisoformat(t_str)] = self.istasyonlar[ist_id]

        oan_res = supabase.table("onceki_ay_nobetleri").select("*").execute()
        self.onceki_ay_kayitlari = oan_res.data # type: ignore

    def nobet_listesi_olustur(self, baslangic_tarihi: date, gun_sayisi: int):
        model = cp_model.CpModel()
        nobetler: Any = {} 
        ceza_istenmeyen_kisi = [] 
        ceza_ekstra_mesai = []    
        
        for gun in range(gun_sayisi):
            aktif_tarih = baslangic_tarihi + timedelta(days=gun)
            poliklinik_calisanlari = []
            yogun_bakim_calisanlari = []

            for dr_id, doktor in self.doktorlar.items():
                nobetler[f"{dr_id}_{gun}"] = model.NewBoolVar(f'nobet_dr{dr_id}_gun{gun}')
                
                if not doktor.nobet_tutabilir_mi(aktif_tarih):
                    model.Add(nobetler[f"{dr_id}_{gun}"] == 0) # type: ignore
                
                istasyon = doktor.gunduz_mesaileri.get(aktif_tarih)
                if istasyon:
                    isim = istasyon.isim.lower()
                    if "konsültasyon" in isim or "nöbet ertesi" in isim:
                        model.Add(nobetler[f"{dr_id}_{gun}"] == 0) # type: ignore
                    elif "poliklinik" in isim or "klinik" in isim:
                        poliklinik_calisanlari.append(dr_id)
                    elif "yoğun bakım" in isim:
                        yogun_bakim_calisanlari.append(dr_id)

            if len(poliklinik_calisanlari) > 1:
                model.Add(sum(nobetler[f"{d}_{gun}"] for d in poliklinik_calisanlari) <= 1)
            if len(yogun_bakim_calisanlari) > 1:
                model.Add(sum(nobetler[f"{d}_{gun}"] for d in yogun_bakim_calisanlari) <= 1)

        for k in self.onceki_ay_kayitlari:
            dr_id, tip = int(k['doktor_id']), int(k['gun_tipi'])
            if dr_id in self.doktorlar:
                if tip == 1: 
                    model.Add(nobetler[f"{dr_id}_0"] == 0) # type: ignore
                    if gun_sayisi > 1: model.Add(nobetler[f"{dr_id}_1"] == 0) # type: ignore
                elif tip == 2: 
                    model.Add(nobetler[f"{dr_id}_0"] == 0) # type: ignore

        for gun in range(gun_sayisi):
            aktif_tarih = baslangic_tarihi + timedelta(days=gun)
            istenen_kisi = 3 if aktif_tarih.weekday() >= 5 else 2
            model.Add(sum(nobetler[f"{dr_id}_{gun}"] for dr_id in self.doktorlar.keys()) == istenen_kisi)
            
            for dr_id, doktor in self.doktorlar.items():
                for istenmeyen_id in doktor.istenmeyen_kisiler:
                    if istenmeyen_id in self.doktorlar:
                        var1 = nobetler[f"{dr_id}_{gun}"] # type: ignore
                        var2 = nobetler[f"{istenmeyen_id}_{gun}"] # type: ignore
                        catisma = model.NewBoolVar(f'catisma_{dr_id}_{istenmeyen_id}_{gun}')
                        model.Add(var1 + var2 - 1 <= catisma)
                        ceza_istenmeyen_kisi.append(catisma)
                        
        for dr_id, doktor in self.doktorlar.items():
            toplam_nobet = sum(nobetler[f"{dr_id}_{gun}"] for gun in range(gun_sayisi))
            fazla_mesai = model.NewIntVar(0, 31, f'fazla_{dr_id}')
            model.Add(fazla_mesai >= toplam_nobet - doktor.aylik_nobet_hedefi)
            ceza_ekstra_mesai.append(fazla_mesai)

            for gun in range(gun_sayisi - 2):
                v1, v2, v3 = nobetler[f"{dr_id}_{gun}"], nobetler[f"{dr_id}_{gun+1}"], nobetler[f"{dr_id}_{gun+2}"] # type: ignore
                model.Add(v1 + v2 + v3 <= 1)

        objective_terms = []
        for gun in range(gun_sayisi):
            for dr_id in self.doktorlar.keys():
                objective_terms.append(random.randint(1, 100) * nobetler[f"{dr_id}_{gun}"]) # type: ignore
        
        model.Maximize(sum(objective_terms) - sum(ceza_istenmeyen_kisi) * 100000 - sum(ceza_ekstra_mesai) * 50000) # type: ignore

        solver = cp_model.CpSolver()
        status = solver.Solve(model)
        
        gun_isimleri = {0: "Pzt", 1: "Sal", 2: "Çar", 3: "Per", 4: "Cum", 5: "Cmt", 6: "Paz"}
        
        if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
            sonuc_listesi = {}
            for gun in range(gun_sayisi):
                aktif_tarih = baslangic_tarihi + timedelta(days=gun)
                # İsimleri alfabetik olarak sıralayıp kaydediyoruz
                nobetci_isimleri = sorted([doktor.isim for dr_id, doktor in self.doktorlar.items() if solver.Value(nobetler[f"{dr_id}_{gun}"]) == 1]) # type: ignore
                sonuc_listesi[str(aktif_tarih)] = {"gun_adi": gun_isimleri[aktif_tarih.weekday()], "nobetciler": nobetci_isimleri}
            
            toplam_kural_ihlali = sum(solver.Value(v) for v in ceza_istenmeyen_kisi)
            uyari_metni = ""
            if toplam_kural_ihlali > 0:
                uyari_metni += f"⚠️ Sistemin tıkanmaması için {toplam_kural_ihlali} adet 'birlikte nöbet tutmama' kuralı esnetildi."
            return {"basari": True, "uyari": uyari_metni if uyari_metni else None, "data": sonuc_listesi}
        else:
            return {"basari": False, "uyari": None, "data": None}

# ==========================================
# 3. FASTAPI WEB SUNUCUSU (API)
# ==========================================
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
supabase_client: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
app = FastAPI()

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

hastane = HastaneSistemi()
hastane.veritabanindan_yukle(supabase_client)

class AyarIstegi(BaseModel): yil: int; ay: int
class IzinIstegi(BaseModel): doktor_id: int; tarihler: list[str]
class GuncelleIstegi(BaseModel): doktor_id: int; idler: list[int]
class MatrisKaydetIstegi(BaseModel): tarih: str; istasyon_id: int; doktor_idler: list[int]
class OncekiAyIstegi(BaseModel): doktor_id: int; gun_tipi: int
class YeniDoktorIstegi(BaseModel): isim: str; kidem: str; rol: str; muaf_mi: bool
class YeniIstasyonIstegi(BaseModel): isim: str; nobete_engel_mi: bool

@app.post("/api/nobet-olustur")
def api_nobet_olustur(istek: AyarIstegi):
    hastane.veritabanindan_yukle(supabase_client)
    if istek.ay == 12: n_y, n_a = istek.yil + 1, 1
    else: n_y, n_a = istek.yil, istek.ay + 1
    gun_sayisi = (date(n_y, n_a, 1) - date(istek.yil, istek.ay, 1)).days
    
    sonuc = hastane.nobet_listesi_olustur(date(istek.yil, istek.ay, 1), gun_sayisi)
    
    if sonuc["basari"]:
        supabase_client.table("aylik_listeler").delete().eq("yil", istek.yil).eq("ay", istek.ay).execute()
        supabase_client.table("aylik_listeler").insert({
            "yil": istek.yil, "ay": istek.ay, "liste_json": sonuc["data"], "uyari_metni": sonuc["uyari"]
        }).execute()
    return sonuc

@app.post("/api/liste-sil")
def api_liste_sil(istek: AyarIstegi):
    supabase_client.table("aylik_listeler").delete().eq("yil", istek.yil).eq("ay", istek.ay).execute()
    return {"basari": True, "mesaj": "Nöbet tablosu veritabanından başarıyla silindi."}

@app.get("/api/mevcut-liste")
def api_mevcut_liste(yil: int, ay: int):
    res = supabase_client.table("aylik_listeler").select("*").eq("yil", yil).eq("ay", ay).execute()
    if res.data:
        return {"basari": True, "data": res.data[0]["liste_json"], "uyari": res.data[0]["uyari_metni"]}
    return {"basari": False, "mesaj": "Henüz bu aya dair nöbet listesi oluşturulmadı. Lütfen daha sonra tekrar kontrol edin."}

@app.get("/api/doktorlar")
def api_doktorlari_getir():
    liste = [{"id": d.id, "isim": d.isim, "rol": d.rol.value, "kidem": d.kidem.name, "muaf_mi": d.muaf_mi} for d in hastane.doktorlar.values()]
    # Python tarafında da alfabetik sıralama garantisi veriyoruz
    liste = sorted(liste, key=lambda x: x['isim'])
    return {"basari": True, "data": liste}

@app.get("/api/istasyonlar")
def api_istasyonlari_getir():
    liste = [{"id": i.id, "isim": i.isim, "engel": i.nobete_engel_mi} for i in hastane.istasyonlar.values()]
    liste = sorted(liste, key=lambda x: x['isim'])
    return {"basari": True, "data": liste}

@app.get("/api/doktor-detay/{doktor_id}")
def api_doktor_detay(doktor_id: int):
    if doktor_id not in hastane.doktorlar: return {"basari": False}
    dr = hastane.doktorlar[doktor_id]
    return {"basari": True, "izinler": [d.isoformat() for d in dr.izinli_gunler], "istenmeyenler": list(dr.istenmeyen_kisiler)}

@app.post("/api/izin-ekle")
def api_izin_ekle(istek: IzinIstegi):
    supabase_client.table("izinli_gunler").delete().eq("doktor_id", istek.doktor_id).execute()
    if istek.tarihler:
        supabase_client.table("izinli_gunler").insert([{"doktor_id": istek.doktor_id, "tarih": t} for t in istek.tarihler]).execute()
    return {"basari": True, "mesaj": "İzinler başarıyla kaydedildi!"}

# YENİ EKLENEN SATIR: Veritabanına yazdıktan sonra Python'un hafızasını da tazele!
    hastane.veritabanindan_yukle(supabase_client) 
    
    return {"basari": True, "mesaj": "İzinler başarıyla kaydedildi!"}

@app.post("/api/istenmeyen-guncelle")
def api_istenmeyen_guncelle(istek: GuncelleIstegi):
    supabase_client.table("istenmeyen_kisiler").delete().eq("doktor_id", istek.doktor_id).execute()
    if istek.idler:
        supabase_client.table("istenmeyen_kisiler").insert([{"doktor_id": istek.doktor_id, "istenmeyen_doktor_id": i} for i in istek.idler]).execute()
    return {"basari": True, "mesaj": "Kısıtlamalar güncellendi!"}

# --- YENİ ADMİN İŞLEMLERİ ---
@app.get("/api/gunduz-mesaileri-matris")
def api_matris(yil: int, ay: int):
    res = supabase_client.table("gunduz_mesaileri").select("*").execute()
    matris = {}
    for r in res.data: # type: ignore
        t = date.fromisoformat(r['tarih'])
        if t.year == yil and t.month == ay:
            t_str, i_id, d_id = str(t), int(r['istasyon_id']), int(r['doktor_id'])
            if t_str not in matris: matris[t_str] = {}
            if i_id not in matris[t_str]: matris[t_str][i_id] = []
            matris[t_str][i_id].append(d_id)
    return {"basari": True, "data": matris}

@app.post("/api/gunduz-mesaisi-kaydet")
def api_gm_kaydet(istek: MatrisKaydetIstegi):
    # İlgili hücreyi temizle
    supabase_client.table("gunduz_mesaileri").delete().eq("tarih", istek.tarih).eq("istasyon_id", istek.istasyon_id).execute()
    # Seçilen doktorları önce diğer istasyonlardan sil (bir doktor aynı gün 2 istasyonda olamaz)
    for d_id in istek.doktor_idler:
        supabase_client.table("gunduz_mesaileri").delete().eq("tarih", istek.tarih).eq("doktor_id", d_id).execute()
    # Yeni kayıtları at
    if istek.doktor_idler:
        data = [{"doktor_id": d, "istasyon_id": istek.istasyon_id, "tarih": istek.tarih} for d in istek.doktor_idler]
        supabase_client.table("gunduz_mesaileri").insert(data).execute()
    return {"basari": True}

@app.get("/api/onceki-ay-getir")
def api_onceki_ay_getir():
    res = supabase_client.table("onceki_ay_nobetleri").select("*, doktorlar(isim)").execute()
    liste = [{"id": o['id'], "doktor": o['doktorlar']['isim'], "tip": "Son Gün" if o['gun_tipi']==1 else "Sondan 2. Gün"} for o in res.data] # type: ignore
    return {"basari": True, "data": liste}

@app.post("/api/onceki-ay-ekle")
def api_onceki_ay_ekle(istek: OncekiAyIstegi):
    try:
        supabase_client.table("onceki_ay_nobetleri").insert({"doktor_id": istek.doktor_id, "gun_tipi": istek.gun_tipi}).execute()
        return {"basari": True}
    except: return {"basari": False}

@app.delete("/api/veri-sil/{tablo}/{id}")
def api_veri_sil(tablo: str, id: int):
    supabase_client.table(tablo).delete().eq("id", id).execute()
    return {"basari": True}

@app.post("/api/doktor-ekle")
def api_doktor_ekle(istek: YeniDoktorIstegi):
    supabase_client.table("doktorlar").insert({"isim": istek.isim, "kidem": istek.kidem, "rol": istek.rol, "muaf_mi": istek.muaf_mi}).execute()
    return {"basari": True}

@app.post("/api/istasyon-ekle")
def api_istasyon_ekle(istek: YeniIstasyonIstegi):
    supabase_client.table("istasyonlar").insert({"isim": istek.isim, "nobete_engel_mi": istek.nobete_engel_mi}).execute()
    return {"basari": True}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
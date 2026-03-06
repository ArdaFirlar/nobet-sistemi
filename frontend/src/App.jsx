import { useState, useEffect } from 'react'

function App() {
  const sistemKoyuMu = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  const [tema, setTema] = useState(sistemKoyuMu ? 'dark' : 'light');

  // Global Ay/Yıl State'leri
  const [takvimAy, setTakvimAy] = useState(new Date().getMonth() + 1);
  const [takvimYil, setTakvimYil] = useState(new Date().getFullYear());

  const [nobetListesi, setNobetListesi] = useState(null)
  const [listeDurumu, setListeDurumu] = useState(null)
  const [yukleniyor, setYukleniyor] = useState(false)
  const [uyari, setUyari] = useState(null)

  const [doktorlar, setDoktorlar] = useState([])
  const [istasyonlar, setIstasyonlar] = useState([])
  const [seciliDoktor, setSeciliDoktor] = useState("")

  const [sifreGirildi, setSifreGirildi] = useState(false)
  const [sifreDeneme, setSifreDeneme] = useState("")

  const [seciliTarihler, setSeciliTarihler] = useState([])
  const [izinMesaj, setIzinMesaj] = useState(null)

  const [seciliIstenmeyenler, setSeciliIstenmeyenler] = useState([])
  const [kuralMesaj, setKuralMesaj] = useState(null)

  // Admin Tab State
  const [adminTab, setAdminTab] = useState("mesai")
  const [matris, setMatris] = useState({})
  const [matrisModalAcik, setMatrisModalAcik] = useState(false)
  const [seciliHucre, setSeciliHucre] = useState({ tarih: "", istasyonId: null, seciliDoktorlar: [] })
  const [oncekiAyNobetleri, setOncekiAyNobetleri] = useState([])
  const [yeniOAN, setYeniOAN] = useState({ doktor_id: "", gun_tipi: "1" })

  // Ekleme Form State'leri
  const [yeniDr, setYeniDr] = useState({ isim: "", kidem: "COMEZ", rol: "Standart", muaf_mi: false })
  const [yeniIst, setYeniIst] = useState({ isim: "", nobete_engel_mi: false })

  const seciliDoktorObj = doktorlar.find(d => d.id.toString() === seciliDoktor.toString());
  const isAdmin = seciliDoktorObj?.rol === 'Admin';
  const isAuthedAdmin = isAdmin && sifreGirildi;

  useEffect(() => { temelVerileriCek(); }, [])

  const temelVerileriCek = () => {
    fetch('http://127.0.0.1:8000/api/doktorlar').then(res => res.json()).then(d => { if (d.basari) setDoktorlar(d.data) })
    fetch('http://127.0.0.1:8000/api/istasyonlar').then(res => res.json()).then(d => { if (d.basari) setIstasyonlar(d.data) })
  }

  useEffect(() => {
    mevcutListeyiGetir();
    if (isAuthedAdmin) adminVerileriniGetir();
  }, [takvimAy, takvimYil, isAuthedAdmin])

  useEffect(() => {
    setIzinMesaj(null); setKuralMesaj(null); setListeDurumu(null); setSifreGirildi(false); setSifreDeneme("");
    if (seciliDoktor) {
      fetch(`http://127.0.0.1:8000/api/doktor-detay/${seciliDoktor}`)
        .then(res => res.json()).then(data => {
          if (data.basari) { setSeciliTarihler(data.izinler); setSeciliIstenmeyenler(data.istenmeyenler); }
        });
      mevcutListeyiGetir();
    } else {
      setSeciliTarihler([]); setSeciliIstenmeyenler([]); setNobetListesi(null);
    }
  }, [seciliDoktor])

  const mevcutListeyiGetir = async () => {
    try {
      const res = await fetch(`http://127.0.0.1:8000/api/mevcut-liste?yil=${takvimYil}&ay=${takvimAy}`);
      const result = await res.json();
      if (result.basari) {
        setNobetListesi(result.data); setUyari(result.uyari); setListeDurumu(null);
      } else {
        setNobetListesi(null); setUyari(null);
        setListeDurumu("⏳ Henüz bu aya dair nöbet listesi oluşturulmadı. Lütfen daha sonra tekrar kontrol edin.");
      }
    } catch (err) { setListeDurumu("Sunucuya bağlanılamadı."); }
  }

  const adminVerileriniGetir = () => {
    fetch(`http://127.0.0.1:8000/api/gunduz-mesaileri-matris?yil=${takvimYil}&ay=${takvimAy}`)
      .then(res => res.json()).then(d => { if (d.basari) setMatris(d.data); })
    fetch('http://127.0.0.1:8000/api/onceki-ay-getir')
      .then(res => res.json()).then(d => { if (d.basari) setOncekiAyNobetleri(d.data); })
  }

  const yeniListeOlustur = async () => {
    setYukleniyor(true); setListeDurumu(null); setUyari(null);
    try {
      const res = await fetch('http://127.0.0.1:8000/api/nobet-olustur', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ yil: takvimYil, ay: takvimAy })
      });
      const result = await res.json();
      if (result.basari) { mevcutListeyiGetir(); }
      else { setListeDurumu("❌ Kurallar çok sıkı, mevcut doktorlarla liste oluşturulamadı."); }
    } catch (err) { setListeDurumu("Sunucu bağlantı hatası."); }
    finally { setYukleniyor(false) }
  }

  const listeSil = async () => {
    if (!window.confirm(`${ayIsimleri[takvimAy - 1]} ${takvimYil} tablosunu silmek istediğinize emin misiniz?`)) return;
    const res = await fetch('http://127.0.0.1:8000/api/liste-sil', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ yil: takvimYil, ay: takvimAy })
    });
    const result = await res.json();
    if (result.basari) mevcutListeyiGetir();
  }

  const hucreTikla = (tarih, istId) => {
    const varOlanlar = matris[tarih]?.[istId] || [];
    setSeciliHucre({ tarih, istasyonId: istId, seciliDoktorlar: varOlanlar });
    setMatrisModalAcik(true);
  }

  const matrisDoktorToggle = (drId) => {
    setSeciliHucre(prev => {
      const list = prev.seciliDoktorlar;
      if (list.includes(drId)) return { ...prev, seciliDoktorlar: list.filter(id => id !== drId) };
      return { ...prev, seciliDoktorlar: [...list, drId] };
    });
  }

  const matrisKaydet = async () => {
    await fetch('http://127.0.0.1:8000/api/gunduz-mesaisi-kaydet', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tarih: seciliHucre.tarih, istasyon_id: seciliHucre.istasyonId, doktor_idler: seciliHucre.seciliDoktorlar })
    });
    setMatrisModalAcik(false);
    adminVerileriniGetir();
  }

  const veriSil = async (tablo, id) => {
    await fetch(`http://127.0.0.1:8000/api/veri-sil/${tablo}/${id}`, { method: 'DELETE' });
    temelVerileriCek(); if (isAuthedAdmin) adminVerileriniGetir();
  }

  const paylasimMetniOlustur = () => {
    if (!nobetListesi) return "";
    let metin = `🏥 ${ayIsimleri[takvimAy - 1]} ${takvimYil} Nöbet Listesi\n\n`;
    Object.entries(nobetListesi).forEach(([tarih, detay]) => {
      metin += `${tarih} (${detay.gun_adi}): ${detay.nobetciler.join(', ')}\n`;
    });
    return metin;
  }

  const ayGunleri = Array.from({ length: new Date(takvimYil, takvimAy, 0).getDate() }, (_, i) => i + 1);
  const startDay = new Date(takvimYil, takvimAy - 1, 1).getDay();
  const boslukSayisi = startDay === 0 ? 6 : startDay - 1;
  const ayIsimleri = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"];

  const digerDoktorlar = doktorlar.filter(dr => dr.id.toString() !== seciliDoktor.toString());

  const isDark = tema === 'dark';
  const themeStyles = {
    appBg: isDark ? '#121212' : '#f0f4f8', textMain: isDark ? '#e0e0e0' : '#2c3e50',
    cardBg: isDark ? '#1e1e1e' : '#ffffff', cardShadow: isDark ? '0 8px 24px rgba(0,0,0,0.5)' : '0 8px 24px rgba(0,0,0,0.08)',
    panelBorder: isDark ? '#333333' : '#e1e8ed', inputBg: isDark ? '#2c2c2c' : '#f7f9fa',
    inputText: isDark ? '#ffffff' : '#000000', btnPrimary: isDark ? '#3f51b5' : '#1976d2',
    btnDanger: isDark ? '#d32f2f' : '#c62828', calendarSelected: isDark ? '#4caf50' : '#2e7d32',
    tableHeader: isDark ? '#333333' : '#f8f9fa', highlightWeekend: isDark ? '#3e2723' : '#fff3e0', highlightMe: isDark ? '#003300' : '#e8f5e9',
    tabBg: isDark ? '#2a2a2a' : '#e3f2fd', tabActive: isDark ? '#3f51b5' : '#1976d2', modalBg: isDark ? 'rgba(0,0,0,0.8)' : 'rgba(0,0,0,0.5)'
  };

  return (
    <>
      <style>{`
        body, html { margin: 0; padding: 0; width: 100%; min-height: 100vh; background-color: ${themeStyles.appBg}; }
        #root { width: 100%; max-width: 100%; margin: 0; padding: 0; text-align: left; }
        * { box-sizing: border-box; }
        .excel-table th, .excel-table td { border: 1px solid ${themeStyles.panelBorder}; padding: 8px; font-size: 14px; }
        .excel-table th { position: sticky; top: 0; background-color: ${themeStyles.tableHeader}; z-index: 10; }
        .excel-table td.clickable:hover { background-color: ${isDark ? '#424242' : '#e3f2fd'}; cursor: pointer; }
      `}</style>

      {/* ========================================== */}
      {/* GÜNCELLENMİŞ MATRİS MODALI (Renk Düzeltmesi) */}
      {/* ========================================== */}
      {matrisModalAcik && (
        <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: themeStyles.modalBg, zIndex: 999, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <div style={{ backgroundColor: themeStyles.cardBg, color: themeStyles.textMain, padding: '25px', borderRadius: '12px', width: '90%', maxWidth: '400px', border: `1px solid ${themeStyles.panelBorder}` }}>
            <h3 style={{ marginTop: 0, color: themeStyles.btnPrimary }}>{seciliHucre.tarih} Görevlileri</h3>
            {/* Burada arkaplanı inputBg ve yazıyı inputText yaparak kontrastı garanti altına aldık */}
            <div style={{ backgroundColor: themeStyles.inputBg, maxHeight: '300px', overflowY: 'auto', marginBottom: '20px', padding: '10px', border: `1px solid ${themeStyles.panelBorder}`, borderRadius: '8px' }}>
              {doktorlar.map(dr => (
                <label key={dr.id} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px', cursor: 'pointer', borderBottom: `1px solid ${themeStyles.panelBorder}`, color: themeStyles.inputText }}>
                  <input type="checkbox" checked={seciliHucre.seciliDoktorlar.includes(dr.id)} onChange={() => matrisDoktorToggle(dr.id)} style={{ width: '18px', height: '18px' }} />
                  <span style={{ fontSize: '16px' }}>{dr.isim}</span>
                </label>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button onClick={matrisKaydet} style={{ flex: 1, padding: '12px', backgroundColor: '#2e7d32', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}>Kaydet</button>
              <button onClick={() => setMatrisModalAcik(false)} style={{ flex: 1, padding: '12px', backgroundColor: themeStyles.btnDanger, color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}>İptal</button>
            </div>
          </div>
        </div>
      )}

      <div style={{ backgroundColor: themeStyles.appBg, color: themeStyles.textMain, minHeight: '100vh', display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '40px 20px', transition: 'all 0.3s ease', fontFamily: 'system-ui, -apple-system, sans-serif' }}>
        <div style={{ width: '100%', maxWidth: '1200px' }}>

          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '15px' }}>
            <h1 style={{ margin: 0, fontSize: '28px' }}>🏥 Nöbet Otomasyon Sistemi</h1>
            <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
              <select value={takvimAy} onChange={e => setTakvimAy(parseInt(e.target.value))} style={{ padding: '8px', borderRadius: '8px', backgroundColor: themeStyles.inputBg, color: themeStyles.inputText, border: `1px solid ${themeStyles.panelBorder}` }}>
                {ayIsimleri.map((ay, i) => <option key={i} value={i + 1}>{ay}</option>)}
              </select>
              <select value={takvimYil} onChange={e => setTakvimYil(parseInt(e.target.value))} style={{ padding: '8px', borderRadius: '8px', backgroundColor: themeStyles.inputBg, color: themeStyles.inputText, border: `1px solid ${themeStyles.panelBorder}` }}>
                {[2025, 2026, 2027].map(y => <option key={y} value={y}>{y}</option>)}
              </select>
              <button onClick={() => setTema(isDark ? 'light' : 'dark')} style={{ background: themeStyles.cardBg, border: `1px solid ${themeStyles.panelBorder}`, borderRadius: '8px', padding: '8px 16px', cursor: 'pointer', color: themeStyles.textMain }}>
                {isDark ? '🌞' : '🌙'}
              </button>
            </div>
          </div>

          <div style={{ backgroundColor: themeStyles.cardBg, border: `1px solid ${themeStyles.panelBorder}`, padding: '30px', borderRadius: '16px', marginBottom: '40px', boxShadow: themeStyles.cardShadow }}>
            <h2 style={{ marginTop: 0, marginBottom: '25px', borderBottom: `2px solid ${themeStyles.panelBorder}`, paddingBottom: '15px' }}>🩺 Doktor Kontrol Paneli</h2>

            <select value={seciliDoktor} onChange={(e) => setSeciliDoktor(e.target.value)} style={{ padding: '12px', fontSize: '16px', borderRadius: '8px', width: '100%', maxWidth: '400px', border: `1px solid ${themeStyles.panelBorder}`, backgroundColor: themeStyles.inputBg, color: themeStyles.inputText, marginBottom: '20px' }}>
              <option value="">👨‍⚕️ Lütfen isminizi seçin...</option>
              {doktorlar.map(dr => <option key={dr.id} value={dr.id}>{dr.isim} {dr.rol === 'Admin' ? '(Yönetici)' : ''}</option>)}
            </select>

            {isAdmin && !sifreGirildi && (
              <div style={{ display: 'flex', gap: '10px', maxWidth: '400px', marginBottom: '20px' }}>
                <input type="password" placeholder="Yönetici Şifresi" value={sifreDeneme} onChange={e => setSifreDeneme(e.target.value)} style={{ padding: '10px', borderRadius: '8px', flex: 1, border: `1px solid ${themeStyles.panelBorder}`, backgroundColor: themeStyles.inputBg, color: themeStyles.inputText }} />
                <button onClick={() => sifreDeneme === "imamoğlu" ? setSifreGirildi(true) : alert("Hatalı!")} style={{ padding: '10px 20px', backgroundColor: themeStyles.btnPrimary, color: 'white', borderRadius: '8px', border: 'none', cursor: 'pointer' }}>Giriş</button>
              </div>
            )}

            {seciliDoktor && (!isAdmin || sifreGirildi) && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '30px' }}>
                <div style={{ backgroundColor: themeStyles.appBg, padding: '20px', borderRadius: '12px', border: `1px solid ${themeStyles.panelBorder}` }}>
                  <h3 style={{ margin: '0 0 15px 0', color: themeStyles.btnPrimary }}>🗓️ İzin Takvimi ({ayIsimleri[takvimAy - 1]} {takvimYil})</h3>
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(7, 1fr)', gap: '8px', marginBottom: '20px' }}>
                    {['Pzt', 'Sal', 'Çar', 'Per', 'Cum', 'Cmt', 'Paz'].map(g => <div key={g} style={{ textAlign: 'center', fontWeight: 'bold', fontSize: '14px', opacity: 0.7 }}>{g}</div>)}
                    {Array(boslukSayisi).fill(null).map((_, i) => <div key={`bos-${i}`} />)}
                    {ayGunleri.map(gun => {
                      const gunStr = `${takvimYil}-${takvimAy.toString().padStart(2, '0')}-${gun.toString().padStart(2, '0')}`;
                      const isSelected = seciliTarihler.includes(gunStr);
                      return <div key={gun} onClick={() => { setIzinMesaj(null); setSeciliTarihler(prev => prev.includes(gunStr) ? prev.filter(t => t !== gunStr) : [...prev, gunStr]); }} style={{ aspectRatio: '1', display: 'flex', alignItems: 'center', justifyContent: 'center', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold', backgroundColor: isSelected ? themeStyles.calendarSelected : themeStyles.inputBg, color: isSelected ? 'white' : themeStyles.inputText, border: `1px solid ${isSelected ? themeStyles.calendarSelected : themeStyles.panelBorder}` }}>{gun}</div>
                    })}
                  </div>
                  <button onClick={async () => { const res = await fetch('http://127.0.0.1:8000/api/izin-ekle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ doktor_id: parseInt(seciliDoktor), tarihler: seciliTarihler }) }); const data = await res.json(); setIzinMesaj(data.basari ? `✅ ${data.mesaj}` : `❌ ${data.mesaj}`); }} style={{ width: '100%', padding: '12px', backgroundColor: themeStyles.btnPrimary, color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}>Kaydet</button>
                  {izinMesaj && <div style={{ marginTop: '10px', textAlign: 'center', fontWeight: 'bold' }}>{izinMesaj}</div>}
                </div>

                <div style={{ backgroundColor: themeStyles.appBg, padding: '20px', borderRadius: '12px', border: `1px solid ${themeStyles.panelBorder}`, display: 'flex', flexDirection: 'column' }}>
                  <h3 style={{ margin: '0 0 10px 0', color: themeStyles.btnDanger }}>🚫 Nöbet Tutmak İstemediğim Kişiler</h3>
                  <p style={{ fontSize: '14px', margin: '0 0 10px 0', color: themeStyles.btnDanger, fontWeight: 'bold' }}>* Ancak yeterli doktor bulunmadığı durumlarda sistem tıkanmamak için size birlikte nöbet yazabilir!</p>
                  <p style={{ fontSize: '12px', margin: '0 0 15px 0', fontStyle: 'italic', opacity: 0.8 }}>👁️ Diğer doktorlar kimleri seçtiğinizi görebilir.</p>

                  <div style={{ flex: 1, overflowY: 'auto', maxHeight: '200px', border: `1px solid ${themeStyles.panelBorder}`, borderRadius: '8px', backgroundColor: themeStyles.inputBg, padding: '10px', marginBottom: '20px' }}>
                    {digerDoktorlar.map(dr => (
                      <label key={dr.id} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '10px', cursor: 'pointer', borderBottom: `1px solid ${themeStyles.panelBorder}`, color: themeStyles.inputText }}>
                        <input type="checkbox" checked={seciliIstenmeyenler.includes(dr.id)} onChange={() => { setKuralMesaj(null); setSeciliIstenmeyenler(prev => prev.includes(dr.id) ? prev.filter(id => id !== dr.id) : [...prev, dr.id]); }} style={{ width: '18px', height: '18px' }} />
                        <span style={{ fontSize: '16px' }}>{dr.isim}</span>
                      </label>
                    ))}
                  </div>
                  <button onClick={async () => { const res = await fetch('http://127.0.0.1:8000/api/istenmeyen-guncelle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ doktor_id: parseInt(seciliDoktor), idler: seciliIstenmeyenler }) }); const data = await res.json(); setKuralMesaj(data.basari ? `✅ ${data.mesaj}` : `❌ ${data.mesaj}`); }} style={{ padding: '12px', backgroundColor: themeStyles.btnDanger, color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}>Kaydet</button>
                  {kuralMesaj && <div style={{ marginTop: '10px', textAlign: 'center', fontWeight: 'bold' }}>{kuralMesaj}</div>}
                </div>
              </div>
            )}
          </div>

          {isAuthedAdmin && (
            <div style={{ backgroundColor: themeStyles.cardBg, border: `2px solid #ff9800`, borderRadius: '16px', marginBottom: '40px', boxShadow: themeStyles.cardShadow, overflow: 'hidden' }}>
              <div style={{ backgroundColor: '#ff9800', color: 'white', padding: '15px 30px' }}><h2 style={{ margin: 0 }}>⚙️ Yönetici Kontrol Paneli</h2></div>

              <div style={{ display: 'flex', borderBottom: `1px solid ${themeStyles.panelBorder}`, backgroundColor: themeStyles.tabBg }}>
                <button onClick={() => setAdminTab("mesai")} style={{ flex: 1, padding: '15px', border: 'none', backgroundColor: adminTab === "mesai" ? themeStyles.cardBg : 'transparent', color: adminTab === "mesai" ? themeStyles.tabActive : themeStyles.textMain, fontWeight: 'bold', cursor: 'pointer', borderTop: adminTab === "mesai" ? `3px solid ${themeStyles.tabActive}` : '3px solid transparent' }}>Gündüz Mesaisi & Matris</button>
                <button onClick={() => setAdminTab("veri")} style={{ flex: 1, padding: '15px', border: 'none', backgroundColor: adminTab === "veri" ? themeStyles.cardBg : 'transparent', color: adminTab === "veri" ? themeStyles.tabActive : themeStyles.textMain, fontWeight: 'bold', cursor: 'pointer', borderTop: adminTab === "veri" ? `3px solid ${themeStyles.tabActive}` : '3px solid transparent' }}>Doktor & İstasyon Yönetimi</button>
              </div>

              <div style={{ padding: '30px' }}>
                {adminTab === "mesai" && (
                  <div>
                    <h3 style={{ marginTop: 0 }}>📊 {ayIsimleri[takvimAy - 1]} {takvimYil} İstasyon Matrisi</h3>
                    <p style={{ fontSize: '14px', opacity: 0.8, marginBottom: '20px' }}>Hücrelere tıklayarak o günkü istasyona görevli doktorları ekleyip çıkarabilirsiniz.</p>

                    <div style={{ overflowX: 'auto', border: `1px solid ${themeStyles.panelBorder}`, borderRadius: '8px', maxHeight: '500px' }}>
                      <table className="excel-table" style={{ width: '100%', minWidth: '800px', borderCollapse: 'collapse', textAlign: 'center' }}>
                        <thead>
                          <tr>
                            <th style={{ backgroundColor: themeStyles.tableHeader, minWidth: '80px' }}>Tarih</th>
                            {istasyonlar.map(ist => <th key={ist.id} style={{ backgroundColor: themeStyles.tableHeader }}>{ist.isim}</th>)}
                          </tr>
                        </thead>
                        <tbody>
                          {ayGunleri.map(gun => {
                            const gunStr = `${takvimYil}-${takvimAy.toString().padStart(2, '0')}-${gun.toString().padStart(2, '0')}`;
                            return (
                              <tr key={gunStr}>
                                <td style={{ fontWeight: 'bold', backgroundColor: themeStyles.tableHeader }}>{gun} {ayIsimleri[takvimAy - 1].substring(0, 3)}</td>
                                {istasyonlar.map(ist => {
                                  const drIds = matris[gunStr]?.[ist.id] || [];
                                  const drNames = drIds.map(id => doktorlar.find(d => d.id === id)?.isim).filter(Boolean).join(" • ");
                                  return (
                                    <td key={ist.id} className="clickable" onClick={() => hucreTikla(gunStr, ist.id)} style={{ color: drNames ? themeStyles.btnPrimary : 'gray', fontWeight: drNames ? 'bold' : 'normal' }}>
                                      {drNames || "+"}
                                    </td>
                                  )
                                })}
                              </tr>
                            )
                          })}
                        </tbody>
                      </table>
                    </div>

                    <div style={{ marginTop: '30px', padding: '20px', backgroundColor: themeStyles.appBg, borderRadius: '8px', border: `1px solid ${themeStyles.panelBorder}` }}>
                      <h4 style={{ margin: '0 0 10px 0' }}>Geçen Ayın Nöbet Devri</h4>
                      <div style={{ display: 'flex', gap: '10px', alignItems: 'center', flexWrap: 'wrap' }}>
                        <select value={yeniOAN.doktor_id} onChange={e => setYeniOAN({ ...yeniOAN, doktor_id: e.target.value })} style={{ padding: '8px', borderRadius: '5px', backgroundColor: themeStyles.inputBg, color: themeStyles.inputText }}>
                          <option value="">Doktor Seçin...</option>
                          {doktorlar.map(dr => <option key={dr.id} value={dr.id}>{dr.isim}</option>)}
                        </select>
                        <select value={yeniOAN.gun_tipi} onChange={e => setYeniOAN({ ...yeniOAN, gun_tipi: e.target.value })} style={{ padding: '8px', borderRadius: '5px', backgroundColor: themeStyles.inputBg, color: themeStyles.inputText }}>
                          <option value="1">Son Gün Tuttu (1. ve 2. gün boş)</option>
                          <option value="2">Sondan 2. Gün Tuttu (Sadece 1. gün boş)</option>
                        </select>
                        <button onClick={async () => { await fetch('http://127.0.0.1:8000/api/onceki-ay-ekle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(yeniOAN) }); adminVerileriniGetir(); }} style={{ padding: '8px 15px', backgroundColor: '#ff9800', color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}>Devret</button>
                      </div>
                      <ul style={{ marginTop: '10px', paddingLeft: '20px', fontSize: '14px' }}>
                        {oncekiAyNobetleri.map(o => <li key={o.id}>{o.doktor} - {o.tip} <button onClick={() => veriSil('onceki_ay_nobetleri', o.id)} style={{ color: 'red', background: 'none', border: 'none', cursor: 'pointer' }}>X</button></li>)}
                      </ul>
                    </div>
                  </div>
                )}

                {adminTab === "veri" && (
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '30px' }}>

                    <div style={{ backgroundColor: themeStyles.appBg, padding: '20px', borderRadius: '8px', border: `1px solid ${themeStyles.panelBorder}` }}>
                      <h4>İstasyon Yönetimi</h4>
                      <div style={{ display: 'flex', gap: '5px', marginBottom: '15px' }}>
                        <input type="text" placeholder="İstasyon Adı" value={yeniIst.isim} onChange={e => setYeniIst({ ...yeniIst, isim: e.target.value })} style={{ padding: '8px', flex: 1, backgroundColor: themeStyles.inputBg, color: themeStyles.inputText }} />
                        <label style={{ display: 'flex', alignItems: 'center', fontSize: '12px' }}><input type="checkbox" checked={yeniIst.nobete_engel_mi} onChange={e => setYeniIst({ ...yeniIst, nobete_engel_mi: e.target.checked })} /> Nöbete Engel?</label>
                        <button onClick={async () => { await fetch('http://127.0.0.1:8000/api/istasyon-ekle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(yeniIst) }); temelVerileriCek(); }} style={{ padding: '8px', backgroundColor: themeStyles.btnPrimary, color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}>Ekle</button>
                      </div>
                      <ul style={{ maxHeight: '200px', overflowY: 'auto', paddingLeft: '15px', fontSize: '14px' }}>
                        {istasyonlar.map(i => <li key={i.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0' }}>{i.isim} {i.engel ? '(Engel)' : ''} <button onClick={() => veriSil('istasyonlar', i.id)} style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer' }}>Sil</button></li>)}
                      </ul>
                    </div>

                    <div style={{ backgroundColor: themeStyles.appBg, padding: '20px', borderRadius: '8px', border: `1px solid ${themeStyles.panelBorder}` }}>
                      <h4>Doktor Yönetimi</h4>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginBottom: '15px' }}>
                        <input type="text" placeholder="Doktor Adı Soyadı" value={yeniDr.isim} onChange={e => setYeniDr({ ...yeniDr, isim: e.target.value })} style={{ padding: '8px', backgroundColor: themeStyles.inputBg, color: themeStyles.inputText }} />
                        <div style={{ display: 'flex', gap: '10px' }}>
                          <select value={yeniDr.kidem} onChange={e => setYeniDr({ ...yeniDr, kidem: e.target.value })} style={{ padding: '8px', flex: 1, backgroundColor: themeStyles.inputBg, color: themeStyles.inputText }}>
                            <option value="EN_COMEZ">En Çömez</option>
                            <option value="COMEZ">Çömez</option>
                            <option value="ASISTAN">Asistan</option>
                          </select>
                          <select value={yeniDr.rol} onChange={e => setYeniDr({ ...yeniDr, rol: e.target.value })} style={{ padding: '8px', flex: 1, backgroundColor: themeStyles.inputBg, color: themeStyles.inputText }}>
                            <option value="Standart">Standart</option>
                            <option value="Admin">Yönetici</option>
                          </select>
                        </div>
                        <label style={{ display: 'flex', alignItems: 'center', fontSize: '14px', color: themeStyles.btnDanger }}><input type="checkbox" checked={yeniDr.muaf_mi} onChange={e => setYeniDr({ ...yeniDr, muaf_mi: e.target.checked })} /> Nöbetten Tamamen Muaf Mı?</label>
                        <button onClick={async () => { await fetch('http://127.0.0.1:8000/api/doktor-ekle', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(yeniDr) }); temelVerileriCek(); }} style={{ padding: '8px', backgroundColor: themeStyles.btnPrimary, color: 'white', border: 'none', borderRadius: '5px', cursor: 'pointer' }}>Ekle</button>
                      </div>
                      <ul style={{ maxHeight: '200px', overflowY: 'auto', paddingLeft: '15px', fontSize: '14px' }}>
                        {doktorlar.map(d => <li key={d.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0' }}>{d.isim} ({d.kidem}) {d.muaf_mi ? '⭐' : ''} <button onClick={() => veriSil('doktorlar', d.id)} style={{ color: 'red', border: 'none', background: 'none', cursor: 'pointer' }}>Sil</button></li>)}
                      </ul>
                    </div>

                  </div>
                )}
              </div>

              <div style={{ padding: '20px 30px', backgroundColor: themeStyles.appBg, borderTop: `1px solid ${themeStyles.panelBorder}`, display: 'flex', gap: '15px', flexWrap: 'wrap' }}>
                <button onClick={yeniListeOlustur} disabled={yukleniyor} style={{ flex: 1, minWidth: '250px', padding: '15px', fontSize: '18px', backgroundColor: '#2e7d32', color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}>
                  {yukleniyor ? '🤖 Hesaplanıyor...' : `🚀 ${ayIsimleri[takvimAy - 1]} ${takvimYil} İçin Algoritmayı Çalıştır`}
                </button>
                <button onClick={listeSil} style={{ padding: '15px', fontSize: '18px', backgroundColor: themeStyles.btnDanger, color: 'white', border: 'none', borderRadius: '8px', cursor: 'pointer', fontWeight: 'bold' }}>
                  🗑️ Tabloyu Sil
                </button>
              </div>
            </div>
          )}

          {listeDurumu && <div style={{ backgroundColor: themeStyles.cardBg, padding: '30px', borderRadius: '16px', boxShadow: themeStyles.cardShadow, textAlign: 'center', fontWeight: 'bold', fontSize: '18px' }}>{listeDurumu}</div>}
          {uyari && <div style={{ backgroundColor: '#fff3cd', color: '#856404', padding: '20px', borderRadius: '12px', marginBottom: '30px', fontWeight: 'bold', boxShadow: themeStyles.cardShadow }}>{uyari}</div>}

          {nobetListesi && (
            <div style={{ backgroundColor: themeStyles.cardBg, padding: '30px', borderRadius: '16px', boxShadow: themeStyles.cardShadow, overflowX: 'auto' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', borderBottom: `2px solid ${themeStyles.panelBorder}`, paddingBottom: '15px', flexWrap: 'wrap', gap: '15px' }}>
                <h2 style={{ margin: 0 }}>📅 {ayIsimleri[takvimAy - 1]} {takvimYil} Nöbet Tablosu</h2>
                <div style={{ display: 'flex', gap: '10px' }}>
                  <a href={`whatsapp://send?text=${encodeURIComponent(paylasimMetniOlustur())}`} style={{ padding: '10px 15px', backgroundColor: '#25D366', color: 'white', textDecoration: 'none', borderRadius: '8px', fontWeight: 'bold' }}>💬 WhatsApp</a>
                  <a href={`mailto:?subject=Aylık Nöbet Listesi&body=${encodeURIComponent(paylasimMetniOlustur())}`} style={{ padding: '10px 15px', backgroundColor: '#ea4335', color: 'white', textDecoration: 'none', borderRadius: '8px', fontWeight: 'bold' }}>📧 E-Posta</a>
                </div>
              </div>

              <table className="excel-table" style={{ width: '100%', textAlign: 'left', borderCollapse: 'collapse' }}>
                <thead><tr style={{ backgroundColor: themeStyles.tableHeader }}><th>Tarih</th><th>Gün</th><th>Nöbetçi Doktorlar</th></tr></thead>
                <tbody>
                  {Object.entries(nobetListesi).map(([tarih, detay]) => {
                    const isWeekend = ['Cmt', 'Paz'].includes(detay.gun_adi);
                    const hasMe = detay.nobetciler.includes(seciliDoktorObj?.isim);
                    let rowBg = 'transparent';
                    if (hasMe) rowBg = themeStyles.highlightMe;
                    else if (isWeekend) rowBg = themeStyles.highlightWeekend;
                    return (
                      <tr key={tarih} style={{ backgroundColor: rowBg }}>
                        <td style={{ fontWeight: 'bold' }}>{tarih}</td>
                        <td style={{ fontWeight: isWeekend ? 'bold' : 'normal', color: isWeekend ? themeStyles.btnDanger : 'inherit' }}>{detay.gun_adi}</td>
                        <td style={{ fontWeight: hasMe ? 'bold' : 'normal', color: hasMe ? '#2e7d32' : 'inherit' }}>{detay.nobetciler.join(' • ')}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              <div style={{ marginTop: '15px', fontSize: '14px', opacity: 0.8, display: 'flex', gap: '20px' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}><div style={{ width: '15px', height: '15px', backgroundColor: themeStyles.highlightWeekend, border: '1px solid gray' }}></div> Hafta Sonu</span>
                {seciliDoktor && <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}><div style={{ width: '15px', height: '15px', backgroundColor: themeStyles.highlightMe, border: '1px solid gray' }}></div> Sizin Nöbetleriniz</span>}
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}
export default App
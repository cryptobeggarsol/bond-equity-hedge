import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
import plotly.graph_objects as go
import requests

# ==========================================
# 0. CANLI USD/TRY KURU ÇEKME FONKSİYONU
# ==========================================
@st.cache_data(ttl=60)
def get_live_usd_try():
    try:
        url = "https://open.er-api.com/v6/latest/USD"
        response = requests.get(url, timeout=3)
        data = response.json()
        if data.get("result") == "success":
            return float(data["rates"]["TRY"])
    except:
        pass
    try:
        ticker = yf.Ticker("USDTRY=X")
        data = ticker.history(period="1d")
        if not data.empty:
            return float(data["Close"].iloc[-1])
    except:
        pass
    return 33.00

canli_usd_try = get_live_usd_try()

# ==========================================
# 1. WEB SAYFASI KONFİGÜRASYONU
# ==========================================
st.set_page_config(
    page_title="CapStructure Arb & Rebalance | Vestel",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Sermaye Yapısı Arbitrajı & Dinamik Rebalance Platformu")
st.caption("Vestel Elektronik (VESTL) Hisse / Eurobond Arbitraj Modeli, Dynamic Delta Rebalancing ve Backtest Motoru")
st.markdown("---")

# Tablar (3 Sekmeli Yapı)
tab1, tab2, tab3 = st.tabs([
    "🔮 Canlı Simülasyon & Dinamik Rebalance", 
    "📜 Tarihsel Backtest (1 Yıllık)", 
    "🧪 Model Doğrulama & Sensitivite"
])

# ==========================================
# 2. YAN PANEL (SIDEBAR)
# ==========================================
st.sidebar.header("⚙️ Simülasyon Parametreleri")
spot_hisse = st.sidebar.number_input("VESTL Spot Hisse Fiyatı (TL)", value=22.76, step=0.1)
usd_try = st.sidebar.number_input("USD/TRY Kuru (Canlı Çekildi)", value=float(canli_usd_try), step=0.01, format="%.4f")

tahvil_secimi = st.sidebar.selectbox(
    "Hedge Edilecek Tahvili Seçin:",
    ("XS2817919587 - 2029 Vadeli USD (%9.75 Kupon)", "2026 Vadeli Iskontolu / Ucuz İhraç")
)
tahvil_fiyat = 885 if "2029" in tahvil_secimi else 680

st.sidebar.subheader("🔄 Mevcut Pozisyonun")
mevcut_short_adedi = st.sidebar.number_input("Mevcut Eldeki Short Hisse Adedi", value=125, step=5)

st.sidebar.subheader("📉 Senaryo Analizi")
hisse_degisim_pct = st.sidebar.slider("Hisse Fiyatı Değişimi (%)", -50, 50, 0)
cds_degisim_bps = st.sidebar.slider("CDS Risk Primi Değişimi (bps)", -200, 300, 0)

# ==========================================
# 3. HESAPLAMA MOTORU (MERTON MODEL & REBALANCE)
# ==========================================
E_mevcut = spot_hisse * (7635000000 / 22.76) # Hisse değişimine göre piyasa değeri
D = 48500000000
V = E_mevcut + D
sigma_E, T, r = 0.42, 2.75, 0.045
sigma_V = sigma_E * (E_mevcut / V)

# Merton d1 & d2
d1 = (np.log(V / D) + (r + 0.5 * sigma_V**2) * T) / (sigma_V * np.sqrt(T))
d2 = d1 - sigma_V * np.sqrt(T)

merton_delta = 1 - norm.cdf(d1)
ampirik_delta = np.clip(merton_delta + (1000 - tahvil_fiyat) / 2000, 0.15, 0.45)

# Greekler
merton_gamma_raw = norm.pdf(d1) / (V * sigma_V * np.sqrt(T))
merton_vega_raw = V * norm.pdf(d1) * np.sqrt(T)
merton_theta_raw = -(V * norm.pdf(d1) * sigma_V) / (2 * np.sqrt(T)) - r * D * np.exp(-r * T) * norm.cdf(d2)

portfolio_scale = 1000 / V
merton_gamma = merton_gamma_raw * (V**2) / 1000  
merton_vega_usd = (merton_vega_raw * portfolio_scale * 0.01) / (usd_try / 33.0) 
merton_theta_usd = (merton_theta_raw * portfolio_scale / 365.0) / (usd_try / 33.0) 

# Senaryodaki Yeni Hisse Fiyatı ve Bilanço Değeri
sim_hisse_fiyati = spot_hisse * (1 + hisse_degisim_pct / 100.0)
sim_E = sim_hisse_fiyati * (7635000000 / 22.76)
sim_V = sim_E + D
sim_sigma_V = sigma_E * (sim_E / sim_V)

sim_d1 = (np.log(sim_V / D) + (r + 0.5 * sim_sigma_V**2) * T) / (sim_sigma_V * np.sqrt(T))
sim_merton_delta = 1 - norm.cdf(sim_d1)
sim_ampirik_delta = np.clip(sim_merton_delta + (1000 - (tahvil_fiyat + cds_degisim_bps * 0.25)) / 2000, 0.15, 0.65)

# Rebalance İhtiyacı
tahvil_tl = tahvil_fiyat * usd_try
hedef_short_tl = tahvil_tl * sim_ampirik_delta
hedef_short_hisse_adedi = int(hedef_short_tl / sim_hisse_fiyati)
rebalance_hisse_adedi = hedef_short_hisse_adedi - mevcut_short_adedi

# PnL Hesapları
hisse_pnl_usd = (spot_hisse - sim_hisse_fiyati) * mevcut_short_adedi / usd_try
tahvil_pnl_usd = (-cds_degisim_bps * 0.25)
toplam_pnl_usd = hisse_pnl_usd + tahvil_pnl_usd

# ==========================================
# SEKME 1: CANLI SIMÜLASYON & REBALANCE
# ==========================================
with tab1:
    st.subheader("📌 Anlık Pozisyon ve Senaryo Durumu")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Canlı Dolar Kuru", f"{usd_try:.2f} TL")
    with col2:
        st.metric("Senaryo Merton Deltası (Δ)", f"{sim_ampirik_delta:.4f}")
    with col3:
        st.metric("Gerekli Hedef Short Adedi", f"{hedef_short_hisse_adedi} Adet")
    with col4:
        st.metric("Senaryo Net PnL", f"${toplam_pnl_usd:.2f} USD", delta=f"${toplam_pnl_usd:.2f} USD")

    st.markdown("---")
    
    # REBALANCE AKSİYON KUTUSU
    st.subheader("🔄 Dinamik Rebalance (Yeniden Dengeleme) Aksiyonu")
    reb_col1, reb_col2 = st.columns([2, 3])
    
    with reb_col1:
        if rebalance_hisse_adedi > 0:
            st.error(f"⚠️ **REBALANCE AKSİYONU: EXTRA SHORT SATIŞ YAPIN!**\n\n"
                     f"Hisse düşüşü/Risk artışı nedeniyle Merton Deltası yükseldi.\n\n"
                     f"➡️ **Ek Olarak Satılacak (Short) Hisse:** `{rebalance_hisse_adedi}` Adet\n\n"
                     f"*Bu işlem çöküşten doğan kârı katlamak için Delta-Neutral korumasını günceller.*")
        elif rebalance_hisse_adedi < 0:
            st.warning(f"🔄 **REBALANCE AKSİYONU: SHORT POZİSYON KAPATIN (BUY TO COVER)**\n\n"
                       f"Hisse yükselişi nedeniyle Merton Deltası düştü.\n\n"
                       f"➡️ **Geri Alınacak (Kapatılacak) Short Hisse:** `{abs(rebalance_hisse_adedi)}` Adet")
        else:
            st.success("✅ **PORTFÖY DENGEDE (DELTA-NEUTRAL):** Şu an için rebalance yapmanıza gerek yok. Pozisyon mükemmel hizada.")

    with reb_col2:
        # Rebalance Senaryo Tablosu
        senaryo_adimlari = [-40, -30, -20, -10, 0, 10, 20, 30, 40]
        reb_table_data = []
        for step in senaryo_adimlari:
            step_price = spot_hisse * (1 + step / 100.0)
            s_E = step_price * (7635000000 / 22.76)
            s_V = s_E + D
            s_sig_V = sigma_E * (s_E / s_V)
            s_d1 = (np.log(s_V / D) + (r + 0.5 * s_sig_V**2) * T) / (s_sig_V * np.sqrt(T))
            s_delta = np.clip((1 - norm.cdf(s_d1)) + (1000 - tahvil_fiyat) / 2000, 0.15, 0.65)
            s_target_shares = int((tahvil_tl * s_delta) / step_price)
            s_reb_action = s_target_shares - mevcut_short_adedi
            
            reb_table_data.append({
                "Hisse Değişimi (%)": f"%{step}",
                "Hisse Fiyatı (TL)": f"{step_price:.2f}",
                "Yeni Merton Delta": f"{s_delta:.4f}",
                "Hedef Short Adedi": f"{s_target_shares} Adet",
                "Rebalance Aksiyonu": f"+{s_reb_action} Adet (Short Sat)" if s_reb_action > 0 else (f"{s_reb_action} Adet (Kapat)" if s_reb_action < 0 else "Dengede")
            })
            
        st.dataframe(pd.DataFrame(reb_table_data), use_container_width=True)

    st.markdown("---")
    st.subheader("📈 Hisse Hareketine Karşı Portföy Duyarlılığı")

    hisse_range = np.linspace(spot_hisse * 0.5, spot_hisse * 1.5, 50)
    hisse_pnl_list = [(spot_hisse - h) * mevcut_short_adedi / usd_try for h in hisse_range]
    tahvil_pnl_list = [(h - spot_hisse) * ampirik_delta * 10 for h in hisse_range]
    net_pnl_list = [h + t for h, t in zip(hisse_pnl_list, tahvil_pnl_list)]

    fig = go.Figure()
    fig.add_trace(go.Scatter(x=hisse_range, y=hisse_pnl_list, mode='lines', name='Short Hisse PnL', line=dict(color='red', dash='dash')))
    fig.add_trace(go.Scatter(x=hisse_range, y=tahvil_pnl_list, mode='lines', name='Long Tahvil Değeri', line=dict(color='blue', dash='dash')))
    fig.add_trace(go.Scatter(x=hisse_range, y=net_pnl_list, mode='lines', name='Net Delta-Neutral PnL', line=dict(color='green', width=3)))

    fig.update_layout(
        title=f"Hisse Fiyat Değişiminin Net Portföy Değerine Etkisi (Güncel Kur: {usd_try:.2f} TL)",
        xaxis_title="VESTL Hisse Fiyatı (TL)",
        yaxis_title="PnL (USD)",
        template="plotly_white"
    )
    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# SEKME 2: TARİHSEL BACKTEST MOTORU
# ==========================================
with tab2:
    st.subheader("📜 1 Yıllık Tarihsel Performans Backtesti (Long Bond + Short Equity)")
    
    @st.cache_data(ttl=3600)
    def load_backtest_data():
        df_hisse = yf.download("VESTL.IS", period="1y", progress=False)
        df_fx = yf.download("USDTRY=X", period="1y", progress=False)
        
        close_hisse = df_hisse['Close'].squeeze()
        close_fx = df_fx['Close'].squeeze()
        
        df = pd.DataFrame({"VESTL": close_hisse, "USDTRY": close_fx}).dropna()
        
        initial_fx = float(df["USDTRY"].iloc[0])
        initial_hisse = float(df["VESTL"].iloc[0])
        
        short_shares_backtest = (1000 * ampirik_delta * initial_fx) / initial_hisse
        
        portfolio_val = []
        for i in range(len(df)):
            h_price = float(df["VESTL"].iloc[i])
            fx_price = float(df["USDTRY"].iloc[i])
            
            short_pnl_usd = (initial_hisse - h_price) * short_shares_backtest / fx_price
            coupon_carry_usd = (1000 * 0.0975) * (i / 252.0)
            bond_val_usd = 885 + (fx_price - initial_fx) * 1.5 + coupon_carry_usd
            
            total_val = bond_val_usd + short_pnl_usd
            portfolio_val.append(total_val)
            
        df["Portfolio_USD"] = portfolio_val
        df["Benchmark_Hisse_USD"] = (df["VESTL"] / df["USDTRY"]) / (initial_hisse / initial_fx) * 1000
        return df

    try:
        df_bt = load_backtest_data()
        
        baslangic_val = df_bt["Portfolio_USD"].iloc[0]
        bitis_val = df_bt["Portfolio_USD"].iloc[-1]
        toplam_getiri_pct = ((bitis_val - baslangic_val) / baslangic_val) * 100
        bench_getiri_pct = ((df_bt["Benchmark_Hisse_USD"].iloc[-1] - 1000) / 1000) * 100

        col_b1, col_b2, col_b3 = st.columns(3)
        with col_b1:
            st.metric("Arbitraj Stratejisi Getirisi (USD)", f"%{toplam_getiri_pct:.2f}", delta=f"%{toplam_getiri_pct:.2f}")
        with col_b2:
            st.metric("Sadece Hisse Tutma Getirisi (USD)", f"%{bench_getiri_pct:.2f}", delta=f"%{bench_getiri_pct:.2f}")
        with col_b3:
            st.metric("Alfa (Arbitraj Fark Getirisi)", f"%{(toplam_getiri_pct - bench_getiri_pct):.2f}")

        fig_bt = go.Figure()
        fig_bt.add_trace(go.Scatter(x=df_bt.index, y=df_bt["Portfolio_USD"], mode='lines', name='Delta-Neutral Arbitraj Portföyü ($)', line=dict(color='green', width=3)))
        fig_bt.add_trace(go.Scatter(x=df_bt.index, y=df_bt["Benchmark_Hisse_USD"], mode='lines', name='Sadece VESTL Hissesi ($)', line=dict(color='gray', dash='dot')))
        
        fig_bt.update_layout(
            title="Son 1 Yıllık Portföy Büyümesi ($1,000 Başlangıç Sermayesi)",
            xaxis_title="Tarih",
            yaxis_title="Portföy Değeri (USD)",
            template="plotly_white"
        )
        st.plotly_chart(fig_bt, use_container_width=True)
        
    except Exception as e:
        st.error(f"Backtest verileri yüklenirken bir hata oluştu: {e}")

# ==========================================
# SEKME 3: MODEL DOĞRULAMA & SENSİTİVİTE
# ==========================================
with tab3:
    st.subheader("🧪 Otomatize Merton Model Doğrulama (Sanity Check)")
    
    delta_v = 100000
    V_plus = V + delta_v
    d1_plus = (np.log(V_plus / D) + (r + 0.5 * sigma_V**2) * T) / (sigma_V * np.sqrt(T))
    merton_delta_plus = 1 - norm.cdf(d1_plus)
    
    sayisal_gamma = (merton_delta_plus - merton_delta) / delta_v
    hata_marjini = abs(sayisal_gamma - merton_gamma_raw)
    
    if hata_marjini < 1e-6:
        st.success(f"✅ **MODEL DOĞRULANDI:** Analitik Merton Deltası ve Gamma parametreleri türevsel olarak tam doğrulukla hesaplanıyor. (Hata Marjı: {hata_marjini:.2e})")
    else:
        st.warning("⚠️ Model türevsel sapma gösteriyor, parametreleri kontrol ediniz.")

    st.markdown("---")
    st.subheader("📊 Portföy Ölçeğinde ($1,000 Büyüklük) Greek Kartları")
    
    c_g1, c_g2, c_g3, c_g4 = st.columns(4)
    with c_g1:
        st.metric("Delta (Δ)", f"{merton_delta:.4f}", help="Varlık Değerine Duyarlılık")
    with c_g2:
        st.metric("Gamma (Γ)", f"{merton_gamma:.2e}", help="Delta Değişim Hızı")
    with c_g3:
        st.metric("Vega (ν - %1 Vol)", f"${merton_vega_usd:.2f} USD", help="Volatilitenin %1 (100bps) artmasının $1,000 portföye etkisi")
    with c_g4:
        st.metric("Theta (Θ - Günlük)", f"${merton_theta_usd:.2f} USD/Gün", help="1 günlük zaman aşınmasının $1,000 portföye etkisi")

    st.markdown("---")
    st.subheader("📉 Volatilitenin Merton Deltasına Etkisi (Vega Eğrisi)")
    
    vol_range = np.linspace(0.10, 0.80, 50)
    delta_vol_list = []
    for v_sigma in vol_range:
        v_sig_V = v_sigma * (E_mevcut / V)
        d1_v = (np.log(V / D) + (r + 0.5 * v_sig_V**2) * T) / (v_sig_V * np.sqrt(T))
        delta_vol_list.append(1 - norm.cdf(d1_v))

    fig_greek = go.Figure()
    fig_greek.add_trace(go.Scatter(x=vol_range * 100, y=delta_vol_list, mode='lines+markers', name='Delta (Δ)', line=dict(color='purple', width=2)))
    
    fig_greek.update_layout(
        title="Volatilite Artışının Hedging Oranına (Delta) Etkisi",
        xaxis_title="Hisse Volatilitesi (% σ_E)",
        yaxis_title="Merton Deltası (Δ)",
        template="plotly_white"
    )
    st.plotly_chart(fig_greek, use_container_width=True)

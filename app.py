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
    page_title="CapStructure Arb & Backtest | Vestel",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Sermaye Yapısı Arbitrajı & Backtest Platformu")
st.caption("Vestel Elektronik (VESTL) Hisse / Eurobond Arbitraj Modeli ve Tarihsel Test Motoru")
st.markdown("---")

# Tablar
tab1, tab2 = st.tabs(["🔮 Canlı Simülasyon & Greekler", "📜 Tarihsel Backtest (1 Yıllık)"])

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

st.sidebar.subheader("📉 Senaryo Analizi")
hisse_degisim_pct = st.sidebar.slider("Hisse Fiyatı Değişimi (%)", -40, 40, 0)
cds_degisim_bps = st.sidebar.slider("CDS Risk Primi Değişimi (bps)", -200, 300, 0)

# ==========================================
# HESAPLAMA MOTORU (MERTON)
# ==========================================
E, D = 7635000000, 48500000000
V = E + D
sigma_E, T, r = 0.42, 2.75, 0.045
sigma_V = sigma_E * (E / V)

d1 = (np.log(V / D) + (r + 0.5 * sigma_V**2) * T) / (sigma_V * np.sqrt(T))
merton_delta = 1 - norm.cdf(d1)
ampirik_delta = np.clip(merton_delta + (1000 - tahvil_fiyat) / 2000, 0.15, 0.45)

tahvil_tl = tahvil_fiyat * usd_try
short_tl = tahvil_tl * ampirik_delta
short_hisse_adedi = int(short_tl / spot_hisse)

sim_hisse_fiyati = spot_hisse * (1 + hisse_degisim_pct / 100.0)
hisse_pnl_usd = (spot_hisse - sim_hisse_fiyati) * short_hisse_adedi / usd_try
tahvil_pnl_usd = (-cds_degisim_bps * 0.25)
toplam_pnl_usd = hisse_pnl_usd + tahvil_pnl_usd

# ==========================================
# SEKME 1: CANLI SIMÜLASYON
# ==========================================
with tab1:
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Canlı Dolar Kuru", f"{usd_try:.2f} TL")
    with col2:
        st.metric("Merton Deltası (Δ)", f"{ampirik_delta:.4f}")
    with col3:
        st.metric("Short Hisse Adedi", f"{short_hisse_adedi} Adet")
    with col4:
        st.metric("Senaryo Net PnL", f"${toplam_pnl_usd:.2f} USD", delta=f"{toplam_pnl_usd:.2f} USD")

    st.markdown("---")
    st.subheader("📈 Hisse Hareketine Karşı Portföy Duyarlılığı")

    hisse_range = np.linspace(spot_hisse * 0.6, spot_hisse * 1.4, 50)
    hisse_pnl_list = [(spot_hisse - h) * short_hisse_adedi / usd_try for h in hisse_range]
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
        # Verileri güvenli şekilde çekiyoruz
        df_hisse = yf.download("VESTL.IS", period="1y", progress=False)
        df_fx = yf.download("USDTRY=X", period="1y", progress=False)
        
        # Sadece Close kolonunu alıp Series yapılarına oturtuyoruz
        close_hisse = df_hisse['Close'].squeeze()
        close_fx = df_fx['Close'].squeeze()
        
        # Ortak tarih dizininde birleştiriyoruz
        df = pd.DataFrame({"VESTL": close_hisse, "USDTRY": close_fx}).dropna()
        
        initial_fx = float(df["USDTRY"].iloc[0])
        initial_hisse = float(df["VESTL"].iloc[0])
        
        # $1,000 başlangıç bütçesi için Short Hisse Adedi
        short_shares_backtest = (1000 * ampirik_delta * initial_fx) / initial_hisse
        
        portfolio_val = []
        for i in range(len(df)):
            h_price = float(df["VESTL"].iloc[i])
            fx_price = float(df["USDTRY"].iloc[i])
            
            # Short hisse PnL ($)
            short_pnl_usd = (initial_hisse - h_price) * short_shares_backtest / fx_price
            
            # Kupon birikimi (%9.75 Kupon)
            coupon_carry_usd = (1000 * 0.0975) * (i / 252.0)
            
            # Sentetik Eurobond Fiyatı
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

        # Backtest Grafiği
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

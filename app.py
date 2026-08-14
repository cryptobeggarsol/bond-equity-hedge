import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np
from scipy.stats import norm
import plotly.graph_objects as go

# ==========================================
# 1. WEB SAYFASI KONFİGÜRASYONU (FRONTEND TASARIM)
# ==========================================
st.set_page_config(
    page_title="CapStructure Arb | Vestel Simülatörü",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Sermaye Yapısı Arbitrajı & Greek Simülatörü")
st.caption("Vestel Elektronik (VESTL) Hisse ve Yurt Dışı Eurobond Arbitraj Modeli")
st.markdown("---")

# ==========================================
# 2. YAN PANEL (SIDEBAR) - INPUT VE SLIDER'LAR
# ==========================================
st.sidebar.header("⚙️ Simülasyon Parametreleri")

# A. Hisse ve Kur Girdileri
spot_hisse = st.sidebar.number_input("VESTL Spot Hisse Fiyatı (TL)", value=22.76, step=0.1)
usd_try = st.sidebar.number_input("USD/TRY Kuru", value=33.00, step=0.5)

# B. Tahvil Seçimi
tahvil_secimi = st.sidebar.selectbox(
    "Hedge Edilecek Tahvili Seçin:",
    ("XS2817919587 - 2029 Vadeli USD (%9.75 Kupon)", "2026 Vadeli Iskontolu / Ucuz İhraç")
)

tahvil_fiyat = 885 if "2029" in tahvil_secimi else 680

# C. Senaryo Slider'ları (Dinamik Etkileşim)
st.sidebar.subheader("📉 Senaryo Analizi")
hisse_degisim_pct = st.sidebar.slider("Hisse Fiyatı Değişimi (%)", -40, 40, 0)
cds_degisim_bps = st.sidebar.slider("CDS Risk Primi Değişimi (bps)", -200, 300, 0)

# ==========================================
# 3. HESAPLAMA MOTORU (MERTON MODEL & GREEKS)
# ==========================================
E = 7635000000      # Özkaynak Piyasa Değeri (TL)
D = 48500000000     # Toplam Borç (TL)
V = E + D
sigma_E = 0.42
sigma_V = sigma_E * (E / V)
T = 2.75
r = 0.045

# Merton d1 & Delta
d1 = (np.log(V / D) + (r + 0.5 * sigma_V**2) * T) / (sigma_V * np.sqrt(T))
merton_delta = 1 - norm.cdf(d1)
ampirik_delta = np.clip(merton_delta + (1000 - tahvil_fiyat) / 2000, 0.15, 0.45)

# Hedge Adedi
tahvil_tl = tahvil_fiyat * usd_try
short_tl = tahvil_tl * ampirik_delta
short_hisse_adedi = int(short_tl / spot_hisse)

# Senaryo Simülasyon PnL
sim_hisse_fiyati = spot_hisse * (1 + hisse_degisim_pct / 100.0)
hisse_pnl_usd = (spot_hisse - sim_hisse_fiyati) * short_hisse_adedi / usd_try
tahvil_pnl_usd = (-cds_degisim_bps * 0.25)  # Yaklaşık CDS duyarlılığı
toplam_pnl_usd = hisse_pnl_usd + tahvil_pnl_usd

# ==========================================
# 4. ARAYÜZ GÖSTERGE KARTLARI (METRICS)
# ==========================================
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric("Seçilen Tahvil Fiyatı", f"${tahvil_fiyat}")
with col2:
    st.metric("Merton Deltası (Δ)", f"{ampirik_delta:.4f}")
with col3:
    st.metric("Short Hisse Adedi", f"{short_hisse_adedi} Adet")
with col4:
    st.metric("Senaryo Net PnL", f"${toplam_pnl_usd:.2f} USD", delta=f"{toplam_pnl_usd:.2f} USD")

st.markdown("---")

# ==========================================
# 5. İNTERAKTİF PnL GRAFİĞİ (PLOTLY)
# ==========================================
st.subheader("📈 Hisse Hareketine Karşı Portföy Duyarlılığı")

hisse_range = np.linspace(spot_hisse * 0.6, spot_hisse * 1.4, 50)
hisse_pnl_list = [(spot_hisse - h) * short_hisse_adedi / usd_try for h in hisse_range]
tahvil_pnl_list = [(h - spot_hisse) * ampirik_delta * 10 for h in hisse_range]  # Koruma etkisi
net_pnl_list = [h + t for h, t in zip(hisse_pnl_list, tahvil_pnl_list)]

fig = go.Figure()
fig.add_trace(go.Scatter(x=hisse_range, y=hisse_pnl_list, mode='lines', name='Short Hisse PnL', line=dict(color='red', dash='dash')))
fig.add_trace(go.Scatter(x=hisse_range, y=tahvil_pnl_list, mode='lines', name='Long Tahvil Değeri', line=dict(color='blue', dash='dash')))
fig.add_trace(go.Scatter(x=hisse_range, y=net_pnl_list, mode='lines', name='Net Delta-Neutral PnL', line=dict(color='green', width=3)))

fig.update_layout(
    title="Hisse Fiyat Değişiminin Net Portföy Değerine Etkisi (Delta Neutral Koruma)",
    xaxis_title="VESTL Hisse Fiyatı (TL)",
    yaxis_title="PnL (USD)",
    template="plotly_white"
)

st.plotly_chart(fig, use_container_width=True)

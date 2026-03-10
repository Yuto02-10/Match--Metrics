import streamlit as st
import pandas as pd
import requests
import io
import math
import random
import plotly.graph_objects as go
import base64
import datetime

# --- ⚙️ 設定エリア ---
GITHUB_USER = "Yuto02-10"   # ユーザー名
GITHUB_REPO = "Match--Metrics"  # リポジトリ名
GITHUB_FOLDER = "試合データ"      # フォルダ名
GITHUB_IMAGE = "打球分析.png"    # 画像ファイル名
GITHUB_TOKEN = None             # Privateなら必須

# --- アプリ設定 ---
st.set_page_config(page_title="チームデータ分析", layout="wide")
st.title("⚾️ チームデータ統合システム (コース拡張版)")

# --- 1. データ取得関数 ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_data(user, repo, folder, token=None):
    base_url = f"https://api.github.com/repos/{user}/{repo}/contents"
    if folder: base_url += f"/{folder}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token: headers["Authorization"] = f"token {token}"
    
    try:
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            return pd.DataFrame(), f"Githubアクセスエラー: {response.status_code}"
        
        files = response.json()
        csv_files = [f for f in files if isinstance(f, dict) and f.get('name', '').endswith('.csv')]
        
        if not csv_files: return pd.DataFrame(), "CSVなし"

        df_list = []
        for f in csv_files:
            if f.get('download_url'):
                r = requests.get(f['download_url'], headers=headers)
                temp = pd.read_csv(io.BytesIO(r.content))
                temp['SourceFile'] = f['name']
                df_list.append(temp)
        
        if df_list:
            return pd.concat(df_list, ignore_index=True), None
        return pd.DataFrame(), "結合失敗"
    except Exception as e:
        return pd.DataFrame(), f"エラー: {e}"

# --- 2. 画像取得関数 ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_image(user, repo, filename, token=None):
    branches = ["main", "master"]
    headers = {}
    if token: headers["Authorization"] = f"token {token}"

    for branch in branches:
        raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/{branch}/{filename}"
        try:
            r = requests.get(raw_url, headers=headers)
            if r.status_code == 200:
                b64_img = base64.b64encode(r.content).decode()
                return f"data:image/png;base64,{b64_img}", None
        except: continue
    return None, "画像が見つかりませんでした"

# --- 3. データ前処理 ---
def clean_and_process(df):
    if df.empty: return df
    
    df.columns = df.columns.str.strip()
    required = ['PitchLocation', 'PitchResult', 'HitResult', 'HitType', 'KorBB', 'Memo', 'Batter', 'Pitcher', 'Date', 'Ball', 'Strike']
    for col in required:
        if col not in df.columns: df[col] = None
    
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    
    str_cols = df.select_dtypes(include=['object']).columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()
        df.loc[df[col] == 'nan', col] = None

    df['PitchLocation'] = pd.to_numeric(df['PitchLocation'], errors='coerce')
    df['is_Zone'] = df['PitchLocation'].isin(range(1, 10))
    
    def check_result(val, keywords):
        if not isinstance(val, str): return False
        return any(k in val for k in keywords)

    df['is_Swing'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振', 'ファール', 'インプレー']))
    df['is_Miss'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振']))
    df['is_Contact'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['ファール', 'インプレー']))

    def parse_xy(memo):
        rank_to_dist = {1: 10, 2: 65, 3: 110, 4: 155, 5: 195, 6: 240, 7: 290}
        dir_to_angle = {
            'B': -46.5, 'C': -42.2, 'D': -38, 'E': -34.2, 'F': -30, 'G': -26,
            'H': -22.15,'I': -18, 'J': -14, 'K': -10, 'L': -6, 'M': -2.5,
            'N': 1.5, 'O': 5.5, 'P': 9.5, 'Q': 13.5, 'R': 17.5, 'S': 21.5,
            'T': 25.5, 'U': 29.5, 'V': 33.5, 'W': 37.5, 'X': 41.5, 'Y': 45.5
        }
        if not isinstance(memo, str) or len(memo) < 2: return pd.Series([None, None])
        try:
            memo = memo.replace(" ", "").upper()
            d = memo[0]
            rank_str = "".join([c for c in memo[1:] if c.isdigit()])
            if not rank_str: return pd.Series([None, None])
            
            rank = int(rank_str)
            angle = dir_to_angle.get(d)
            if angle is not None and rank in rank_to_dist:
                angle += random.uniform(-0.05, 0.05)
                dist = rank_to_dist[rank] * random.uniform(0.9, 1.1)
                rad = math.radians(angle)
                return pd.Series([round(dist*1.2*math.sin(rad),2), round(dist*0.8*math.cos(rad),2)])
        except: pass
        return pd.Series([None, None])

    df[['打球X', '打球Y']] = df['Memo'].apply(parse_xy)
    return df

# --- メイン処理 ---
st.sidebar.header("📁 データ読み込み")

with st.spinner("データ取得中..."):
    df, err = fetch_github_data(GITHUB_USER, GITHUB_REPO, GITHUB_FOLDER, GITHUB_TOKEN)

if df.empty:
    st.error(f"データ取得失敗: {err}")
    st.info("手動でCSVをアップロードしてください")
    uploaded = st.file_uploader("CSVアップロード", accept_multiple_files=True)
    if uploaded:
        df = pd.concat([pd.read_csv(f).assign(SourceFile=f.name) for f in uploaded], ignore_index=True)
    else:
        st.stop()

df = clean_and_process(df)

# --- 📅 期間選択機能 ---
st.sidebar.markdown("---")
st.sidebar.header("📅 期間設定")
valid_dates = df['Date'].dropna()

if not valid_dates.empty:
    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()
    start_date, end_date = st.sidebar.date_input("分析期間を選択", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    mask = (df['Date'].dt.date >= start_date) & (df['Date'].dt.date <= end_date)
    df = df.loc[mask]
    st.sidebar.success(f"期間: {start_date} ～ {end_date}")

bg_image, img_err = fetch_github_image(GITHUB_USER, GITHUB_REPO, GITHUB_IMAGE, GITHUB_TOKEN)

# --- 分析画面 ---
players = sorted(list(set(df['Batter'].dropna().unique()) | set(df['Pitcher'].dropna().unique())))
if not players:
    st.warning("選択された期間に該当する選手データがありません。")
    st.stop()

selected_player = st.selectbox("選手を選択", players)
b_df = df[df['Batter'] == selected_player]

tab1, tab2 = st.tabs(["📊 詳細成績・グラフ", "🏟 打球方向"])

with tab1:
    if b_df.empty:
        st.warning(f"{selected_player} 選手の期間内データはありません")
    else:
        # 指標計算
        pa_rows = b_df[(b_df['KorBB'].notna()) | (b_df['HitResult'].notna()) | (b_df['PitchResult'].astype(str).str.contains('死球'))]
        pa = len(pa_rows)
        hits = b_df['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打']).sum()
        bb = b_df['KorBB'].isin(['四球']).sum()
        hbp = b_df['PitchResult'].astype(str).str.contains('死球').sum()
        so = b_df['KorBB'].astype(str).str.contains('三振').sum()
        sac = b_df['HitResult'].isin(['犠打', '犠飛']).sum()
        ab = pa - bb - hbp - sac
        
        total_pitches = len(b_df)
        swings = b_df['is_Swing'].sum()
        contact_cnt = b_df['is_Contact'].sum()
        misses = b_df['is_Miss'].sum()
        
        z_df = b_df[b_df['is_Zone']]
        z_total = len(z_df)
        z_swings = z_df['is_Swing'].sum()
        z_contact = z_df['is_Contact'].sum()
        z_takes = z_total - z_swings
        
        o_df = b_df[~b_df['is_Zone']]
        o_total = len(o_df)
        o_swings = o_df['is_Swing'].sum()
        o_contact = o_df['is_Contact'].sum()

        def pct(n, d): return (n / d * 100) if d > 0 else 0
        
        stats = {
            "試合数": b_df['Date'].nunique() if 'Date' in b_df.columns else 1,
            "打席数": pa,
            "打率": f"{hits/ab:.3f}" if ab > 0 else "-",
            "四球率": f"{pct(bb, pa):.1f}%",
            "三振率": f"{pct(so, pa):.1f}%",
            "スイング率": f"{pct(swings, total_pitches):.1f}%",
            "ストライク見逃し率": f"{pct(z_takes, z_total):.1f}%",
            "O-Swing%": f"{pct(o_swings, o_total):.1f}%",
            "Z-Swing%": f"{pct(z_swings, z_total):.1f}%",
            "SwStr%": f"{pct(misses, total_pitches):.1f}%",
            "O-Contact%": f"{pct(o_contact, o_swings):.1f}%",
            "Z-Contact%": f"{pct(z_contact, z_swings):.1f}%",
            "Contact%": f"{pct(contact_cnt, swings):.1f}%"
        }
        
        st.subheader("打撃成績詳細")
        st.table(pd.DataFrame([stats]))
        
        # ==========================================
        # 📊 追加グラフセクション
        # ==========================================
        st.markdown("---")
        st.subheader("📈 アプローチ分析")

        # 1. カウント別
        c_df = b_df.copy()
        c_df['Count'] = c_df['Ball'].astype(str) + "-" + c_df['Strike'].astype(str)
        count_stats = []
        for c in sorted(c_df['Count'].unique()):
            temp = c_df[c_df['Count'] == c]
            z_temp = temp[temp['is_Zone']]
            
            t_swings = temp['is_Swing'].sum()
            t_z_takes = len(z_temp) - z_temp['is_Swing'].sum()
            
            s_rate = pct(t_swings, len(temp))
            t_rate = pct(t_z_takes, len(z_temp))
            
            count_stats.append({"Count": c, "スイング率(%)": s_rate, "見逃し率(%)": t_rate, "投球数": len(temp)})

        if count_stats:
            count_df = pd.DataFrame(count_stats)
            fig_count = go.Figure()
            fig_count.add_trace(go.Bar(x=count_df['Count'], y=count_df['スイング率(%)'], name='スイング率', marker_color='#1f77b4'))
            fig_count.add_trace(go.Bar(x=count_df['Count'], y=count_df['見逃し率(%)'], name='見逃し率(Z)', marker_color='#ff7f0e'))
            fig_count.update_layout(title="カウント別 スイング率・ストライク見逃し率", barmode='group', xaxis_title="ボール - ストライク", yaxis_title="割合(%)")
            st.plotly_chart(fig_count, use_container_width=True)


        # コース別グラフの配置定義 (1〜9がストライクゾーン、11〜14がボールゾーン)
        # 座標系: x=1,2,3 y=1,2,3 がストライクゾーン
        zone_map = {
            1: (1, 3), 2: (2, 3), 3: (3, 3),
            4: (1, 2), 5: (2, 2), 6: (3, 2),
            7: (1, 1), 8: (2, 1), 9: (3, 1),
            11: (2, 4.2),  # 高め
            13: (2, -0.2), # 低め
            12: (-0.2, 2), # 12番コース (左側)
            14: (4.2, 2)   # 14番コース (右側)
        }
        
        zone_names = {11: "高め", 13: "低め", 12: "コース12", 14: "コース14"}

        # ストライクゾーンを描くための枠線 (3x3グリッド)
        board_shapes = [
            # 外枠
            dict(type="rect", x0=0.5, y0=0.5, x1=3.5, y1=3.5, line=dict(color="black", width=2)),
            # 縦線
            dict(type="line", x0=1.5, y0=0.5, x1=1.5, y1=3.5, line=dict(color="gray", width=1, dash="dash")),
            dict(type="line", x0=2.5, y0=0.5, x1=2.5, y1=3.5, line=dict(color="gray", width=1, dash="dash")),
            # 横線
            dict(type="line", x0=0.5, y0=1.5, x1=3.5, y1=1.5, line=dict(color="gray", width=1, dash="dash")),
            dict(type="line", x0=0.5, y0=2.5, x1=3.5, y1=2.5, line=dict(color="gray", width=1, dash="dash")),
        ]

        col1, col2 = st.columns(2)

        # 2. コース別 スイング・見逃し率
        with col1:
            st.markdown("**コース別 スイング率 / 見逃し率**")
            zone_texts = []
            xs, ys = [], []
            
            for z in [1,2,3,4,5,6,7,8,9, 11,12,13,14]:
                z_data = b_df[b_df['PitchLocation'] == z]
                # ボールゾーンのみラベル名を追加
                prefix = f"<b>{zone_names[z]}</b><br>" if z in zone_names else ""
                
                if not z_data.empty:
                    s_rate = pct(z_data['is_Swing'].sum(), len(z_data))
                    t_rate = pct(len(z_data) - z_data['is_Swing'].sum(), len(z_data))
                    txt = f"{prefix}振:{s_rate:.0f}%<br>見:{t_rate:.0f}%"
                else:
                    txt = f"{prefix}-"
                
                x, y = zone_map[z]
                xs.append(x)
                ys.append(y)
                zone_texts.append(txt)

            fig_zone1 = go.Figure(go.Scatter(
                x=xs, y=ys, mode="text", text=zone_texts, textfont=dict(size=12, color="black")
            ))
            fig_zone1.update_layout(
                xaxis=dict(range=[-1, 5], showticklabels=False, showgrid=False, zeroline=False),
                yaxis=dict(range=[-1, 5], showticklabels=False, showgrid=False, zeroline=False),
                width=350, height=350, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="whitesmoke",
                shapes=board_shapes
            )
            st.plotly_chart(fig_zone1, use_container_width=True)

        # 3. コース別 打球傾向
        with col2:
            st.markdown("**コース別 ゴロ / フライ / ライナー 発生率**")
            hit_texts = []
            h_xs, h_ys = [], []
            
            for z in [1,2,3,4,5,6,7,8,9, 11,12,13,14]:
                z_data = b_df[(b_df['PitchLocation'] == z) & (b_df['HitType'].notna())]
                prefix = f"<b>{zone_names[z]}</b><br>" if z in zone_names else ""
                
                if not z_data.empty:
                    goro = pct((z_data['HitType'] == 'ゴロ').sum(), len(z_data))
                    fly = pct((z_data['HitType'] == 'フライ').sum(), len(z_data))
                    liner = pct((z_data['HitType'] == 'ライナー').sum(), len(z_data))
                    txt = f"{prefix}ゴ:{goro:.0f}%<br>フ:{fly:.0f}%<br>ラ:{liner:.0f}%"
                else:
                    txt = f"{prefix}-"
                
                x, y = zone_map[z]
                h_xs.append(x)
                h_ys.append(y)
                hit_texts.append(txt)

            fig_zone2 = go.Figure(go.Scatter(
                x=h_xs, y=h_ys, mode="text", text=hit_texts, textfont=dict(size=11, color="black")
            ))
            fig_zone2.update_layout(
                xaxis=dict(range=[-1, 5], showticklabels=False, showgrid=False, zeroline=False),
                yaxis=dict(range=[-1, 5], showticklabels=False, showgrid=False, zeroline=False),
                width=350, height=350, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="whitesmoke",
                shapes=board_shapes
            )
            st.plotly_chart(fig_zone2, use_container_width=True)

        with st.expander("データログ"):
            cols = ['Date', 'Inning', 'Pitcher', 'PitchResult', 'HitResult', 'HitType', 'Memo']
            st.dataframe(b_df[[c for c in cols if c in df.columns]].fillna('').sort_values('Date'))

with tab2:
    chart_df = b_df.dropna(subset=['打球X', '打球Y'])
    
    if chart_df.empty:
        st.warning("この期間の打球データがありません")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df['打球X'], y=chart_df['打球Y'],
            mode='markers',
            marker=dict(size=12, color='blue', line=dict(width=1, color='white')),
            text=chart_df['Memo'],
            name=selected_player
        ))
        
        layout = dict(
            xaxis=dict(range=[-200, 200], showticklabels=False, fixedrange=True),
            yaxis=dict(range=[-20, 240], showticklabels=False, fixedrange=True),
            width=600, height=600,
            plot_bgcolor="white",
            margin=dict(l=0, r=0, t=0, b=0)
        )
        if bg_image:
            layout['images'] = [dict(
                source=bg_image, xref="x", yref="y",
                x=-292.5, y=296.25, sizex=585, sizey=315,
                sizing="stretch", layer="below"
            )]
            
        fig.update_layout(**layout)
        st.plotly_chart(fig, use_container_width=True)















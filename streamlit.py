import streamlit as st
import pandas as pd
import requests
import io
import math
import random
import plotly.graph_objects as go
import base64

# --- ⚙️ 設定エリア ---
GITHUB_USER = ""   # ユーザー名
GITHUB_REPO = ""  # リポジトリ名
GITHUB_FOLDER = "試合データ"       # フォルダ名
GITHUB_IMAGE = "打球分析.png"    # 画像ファイル名
GITHUB_TOKEN = None             # Privateなら必須

# --- アプリ設定 ---
st.set_page_config(page_title="チームデータ分析", layout="wide")
st.title("選手分析")

# --- 文字コード自動判定でCSVを安全に読み込む関数 ---
def read_csv_robust(file_bytes):
    try:
        return pd.read_csv(io.BytesIO(file_bytes), encoding='utf-8')
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(file_bytes), encoding='cp932')

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
                temp = read_csv_robust(r.content)
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
    
    df.columns = df.columns.astype(str).str.strip().str.replace('　', '')
    df = df.loc[:, ~df.columns.duplicated(keep='first')].copy()
    
    column_mapping = {
        'イニング': 'Inning', 'ボール': 'Ball', 'ストライク': 'Strike',
        '投手': 'Pitcher', '打者': 'Batter', '球種': 'PitchType',
        '投球位置': 'PitchLocation', '投球結果': 'PitchResult',
        '三振四球': 'KorBB', '打撃結果': 'HitResult', '打球タイプ': 'HitType',
        'メモ': 'Memo', '日付': 'Date', 'Ｄａｔｅ': 'Date', 'date': 'Date',
        'プレーアウト数': 'PlayOuts', '打者左右': 'BatterLR'
    }
    df = df.rename(columns=column_mapping)
    df = df.loc[:, ~df.columns.duplicated(keep='first')].copy()

    # 🌟【変更】BatterLR を必須列に追加
    required = ['PitchLocation', 'PitchResult', 'HitResult', 'HitType', 'KorBB', 'Memo', 'Batter', 'Pitcher', 'Date', 'Ball', 'Strike', 'PlayOuts', 'SourceFile', 'BatterLR']
    for col in required:
        if col not in df.columns: df[col] = None

    # 選手名のスペース・空白を完全に除去
    if 'Batter' in df.columns:
        df['Batter'] = df['Batter'].astype(str).str.replace(r'\s+', '', regex=True)
    if 'Pitcher' in df.columns:
        df['Pitcher'] = df['Pitcher'].astype(str).str.replace(r'\s+', '', regex=True)
    
    # 日付のオートフィル
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    if 'SourceFile' in df.columns:
        df['Date'] = df.groupby('SourceFile')['Date'].transform(lambda x: x.ffill().bfill())

    # 🌟【追加】BatterLR（打者の左右）の表記揺れを「R」または「L」に統一
    if 'BatterLR' in df.columns:
        df['BatterLR'] = df['BatterLR'].astype(str).str.upper().str.strip()
        df['BatterLR'] = df['BatterLR'].replace({'RIGHT': 'R', 'LEFT': 'L', '右': 'R', '左': 'L'})

    # 文字データの空白やハイフンをクリア
    str_cols = df.select_dtypes(include=['object']).columns
    for col in str_cols:
        if isinstance(df[col], pd.Series):
            df[col] = df[col].astype(str).str.strip()
            df.loc[df[col].isin(['nan', 'None', '', '-', '不明']), col] = None

    df['PitchLocation'] = pd.to_numeric(df['PitchLocation'], errors='coerce')
    df['is_Zone'] = df['PitchLocation'].isin(range(1, 10))
    df['PlayOuts'] = pd.to_numeric(df['PlayOuts'], errors='coerce').fillna(0)
    
    def check_result(val, keywords):
        if not isinstance(val, str): return False
        return any(k in val for k in keywords)

    df['is_Swing'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振', 'ファール', 'ファウル', 'インプレー']))
    df['is_Miss'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振']))
    df['is_Contact'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['ファール', 'ファウル', 'インプレー']))

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

# --- 共通のグラフ設定群 ---
def pct(n, d): return (n / d * 100) if d > 0 else 0

zone_map = {1: (1, 3), 2: (2, 3), 3: (3, 3), 4: (1, 2), 5: (2, 2), 6: (3, 2), 7: (1, 1), 8: (2, 1), 9: (3, 1), 11: (0.2, 4.2), 12: (3.8, 4.2), 13: (0.2, -0.2), 14: (3.8, -0.2)}
zone_names = {11: "左上", 12: "右上", 13: "左下", 14: "右下"}

board_shapes = [
    dict(type="rect", x0=0.5, y0=0.5, x1=3.5, y1=3.5, line=dict(color="black", width=2)),
    dict(type="line", x0=1.5, y0=0.5, x1=1.5, y1=3.5, line=dict(color="gray", width=1, dash="dash")),
    dict(type="line", x0=2.5, y0=0.5, x1=2.5, y1=3.5, line=dict(color="gray", width=1, dash="dash")),
    dict(type="line", x0=0.5, y0=1.5, x1=3.5, y1=1.5, line=dict(color="gray", width=1, dash="dash")),
    dict(type="line", x0=0.5, y0=2.5, x1=3.5, y1=2.5, line=dict(color="gray", width=1, dash="dash")),
]

# --- メイン処理開始 ---
st.sidebar.header("📁 設定・読み込み")

if st.sidebar.button("🔄 データを最新に更新"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("GitHubからデータ取得中..."):
    df_github, err = fetch_github_data(GITHUB_USER, GITHUB_REPO, GITHUB_FOLDER, GITHUB_TOKEN)

uploaded = st.sidebar.file_uploader("📂 追加CSVを直接アップロード", accept_multiple_files=True)
df_local = pd.DataFrame()

if uploaded:
    local_dfs = []
    for f in uploaded:
        temp = read_csv_robust(f.read())
        temp['SourceFile'] = f.name
        local_dfs.append(temp)
    df_local = pd.concat(local_dfs, ignore_index=True)

if not df_local.empty:
    if not df_github.empty:
        df = pd.concat([df_github, df_local], ignore_index=True)
    else:
        df = df_local
else:
    df = df_github

if df.empty:
    st.error("データが見つかりません。")
    st.stop()

df = clean_and_process(df)

with st.expander("🛠 データの読み込み状況（確認用）", expanded=False):
    st.write(f"読み込まれた全データ: **{len(df)}行**")
    st.write("▼ データの先頭3行")
    st.dataframe(df.head(3))

# --- 📅 期間選択機能 ---
valid_dates = df['Date'].dropna()
if not valid_dates.empty:
    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()
    
    selected_dates = st.sidebar.date_input("📅 分析期間", value=(min_date, max_date), min_value=min_date, max_value=max_date)
    
    if len(selected_dates) == 2:
        start_date, end_date = selected_dates
    else:
        start_date = selected_dates[0]
        end_date = selected_dates[0]
        
    df = df[(df['Date'].dt.date >= start_date) & (df['Date'].dt.date <= end_date)]
else:
    st.sidebar.warning("⚠️ 有効なDate（日付）データが見つかりません。全期間を表示します。")

bg_image, img_err = fetch_github_image(GITHUB_USER, GITHUB_REPO, GITHUB_IMAGE, GITHUB_TOKEN)

st.sidebar.markdown("---")
analysis_mode = st.sidebar.radio("🔍 分析モード", ["👤 打者分析", "⚾ 投手分析"])
st.sidebar.markdown("---")

if analysis_mode == "👤 打者分析":
    players = sorted(list(df['Batter'].dropna().unique()))
    if not players: st.warning("期間内に打者データがありません。"); st.stop()
    selected_player = st.sidebar.selectbox("打者を選択", players)
    target_df = df[df['Batter'] == selected_player]
    st.header(f"👤 {selected_player} 選手の打撃分析")
else:
    players = sorted(list(df['Pitcher'].dropna().unique()))
    if not players: st.warning("期間内に投手データがありません。"); st.stop()
    selected_player = st.sidebar.selectbox("投手を選択", players)
    target_df = df[df['Pitcher'] == selected_player]
    st.header(f"⚾ {selected_player} 投手の投球分析")

tab1, tab2 = st.tabs(["📊 詳細成績・グラフ", "🏟 打球方向"])

with tab1:
    if target_df.empty:
        st.warning("この期間のデータはありません")
    else:
        pa_rows = target_df[(target_df['KorBB'].notna()) | (target_df['HitResult'].notna()) | (target_df['PitchResult'].astype(str).str.contains('死球'))]
        pa = len(pa_rows)
        hits = target_df['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打']).sum()
        hr = target_df['HitResult'].isin(['本塁打']).sum()
        bb = target_df['KorBB'].astype(str).str.contains('四球').sum()
        hbp = target_df['PitchResult'].astype(str).str.contains('死球').sum()
        so = target_df['KorBB'].astype(str).str.contains('三振').sum()
        sac = target_df['HitResult'].isin(['犠打', '犠飛']).sum()
        ab = pa - bb - hbp - sac
        
        total_pitches = len(target_df)
        swings = target_df['is_Swing'].sum()
        contact_cnt = target_df['is_Contact'].sum()
        misses = target_df['is_Miss'].sum()
        
        z_df = target_df[target_df['is_Zone']]
        z_total = len(z_df)
        z_swings = z_df['is_Swing'].sum()
        z_contact = z_df['is_Contact'].sum()
        z_takes = z_total - z_swings
        
        o_df = target_df[~target_df['is_Zone']]
        o_total = len(o_df)
        o_swings = o_df['is_Swing'].sum()

        batted_balls = target_df[target_df['HitType'].notna()]
        total_batted = len(batted_balls)
        gb = (batted_balls['HitType'] == 'ゴロ').sum()
        fb = (batted_balls['HitType'] == 'フライ').sum()
        ld = (batted_balls['HitType'] == 'ライナー').sum()

        if analysis_mode == "👤 打者分析":
            stats = {
                "試合数": target_df['Date'].nunique() if 'Date' in target_df.columns else 1,
                "打席数": pa,
                "打率": f"{hits/ab:.3f}" if ab > 0 else "-",
                "四球率": f"{pct(bb, pa):.1f}%",
                "三振率": f"{pct(so, pa):.1f}%",
                "スイング率": f"{pct(swings, total_pitches):.1f}%",
                "ストライク見逃し率": f"{pct(z_takes, z_total):.1f}%",
                "O-Swing%": f"{pct(o_swings, o_total):.1f}%",
                "Z-Swing%": f"{pct(z_swings, z_total):.1f}%",
                "SwStr%": f"{pct(misses, total_pitches):.1f}%",
                "Contact%": f"{pct(contact_cnt, swings):.1f}%"
            }
            st.subheader("打撃成績")
            
        else:
            outs = target_df['PlayOuts'].sum()
            if outs == 0 and pa > 0: 
                outs = so + target_df['HitResult'].isin(['凡打', 'アウト', '併殺打']).sum() + target_df['HitResult'].isin(['犠打', '犠飛']).sum()
                
            ip_full = int(outs // 3)
            ip_frac = int(outs % 3)
            ip_display = f"{ip_full}.{ip_frac}"
            ip_math = outs / 3.0
            
            fip = ((13 * hr + 3 * (bb + hbp) - 2 * so) / ip_math + 3.20) if ip_math > 0 else 0.0
            
            stats = {
                "試合数": target_df['Date'].nunique() if 'Date' in target_df.columns else 1,
                "投球イニング": ip_display,
                "K%": f"{pct(so, pa):.1f}%",
                "BB%": f"{pct(bb, pa):.1f}%",
                "K-BB%": f"{pct(so-bb, pa):.1f}%",
                "chase%": f"{pct(o_swings, o_total):.1f}%",
                "whiff%": f"{pct(misses, total_pitches):.1f}%",
                "FIP": f"{fip:.2f}",
                "ゴロ%": f"{pct(gb, total_batted):.1f}%",
                "フライ%": f"{pct(fb, total_batted):.1f}%",
                "ライナー%": f"{pct(ld, total_batted):.1f}%"
            }
            st.subheader("投球成績 (Advanced)")

        st.table(pd.DataFrame([stats]))
        
        st.markdown("---")
        st.subheader("📈 アプローチ・傾向分析")

        c_df = target_df.copy()
        c_df['Count'] = c_df['Ball'].astype(str) + "-" + c_df['Strike'].astype(str)
        count_stats = []
        for c in sorted(c_df['Count'].unique()):
            temp = c_df[c_df['Count'] == c]
            z_temp = temp[temp['is_Zone']]
            
            t_swings = temp['is_Swing'].sum()
            t_z_takes = len(z_temp) - z_temp['is_Swing'].sum()
            t_all_takes = len(temp) - t_swings
            
            s_rate = pct(t_swings, len(temp))
            z_t_rate = pct(t_z_takes, len(z_temp))
            all_t_rate = pct(t_all_takes, len(temp))
            
            count_stats.append({
                "Count": c, 
                "スイング率(%)": s_rate, 
                "ゾーン内見逃し率(%)": z_t_rate, 
                "全体見逃し率(%)": all_t_rate, 
                "球数": len(temp)
            })

        if count_stats:
            count_df = pd.DataFrame(count_stats)
            fig_count = go.Figure()
            
            label_s = "スイング率" if analysis_mode == "👤 打者分析" else "打者のスイング率"
            label_zt = "ゾーン内見逃し率" if analysis_mode == "👤 打者分析" else "打者のゾーン内見逃し率"
            label_at = "全体見逃し率" if analysis_mode == "👤 打者分析" else "打者の全体見逃し率"

            fig_count.add_trace(go.Bar(x=count_df['Count'], y=count_df['スイング率(%)'], name=label_s, marker_color='#1f77b4'))
            fig_count.add_trace(go.Bar(x=count_df['Count'], y=count_df['ゾーン内見逃し率(%)'], name=label_zt, marker_color='#ff7f0e'))
            fig_count.add_trace(go.Bar(x=count_df['Count'], y=count_df['全体見逃し率(%)'], name=label_at, marker_color='#2ca02c'))
            
            fig_count.update_layout(title="カウント別 スイング・見逃し傾向", barmode='group', xaxis_title="ボール - ストライク", yaxis_title="割合(%)")
            st.plotly_chart(fig_count, use_container_width=True)

        # 🌟【追加】打者の左右でコース別グラフのデータを絞り込む機能
        st.markdown("---")
        st.subheader("🎯 コース別 アプローチ・打球傾向")
        
        lr_options = {"全体": "ALL", "右打者 (R)": "R", "左打者 (L)": "L"}
        selected_lr_label = st.radio("📊 表示する打者の左右を選択", list(lr_options.keys()), horizontal=True)
        selected_lr = lr_options[selected_lr_label]

        # 選択された左右に応じてデータをフィルタリング（全体ならそのまま）
        zone_df = target_df.copy()
        if selected_lr != "ALL":
            zone_df = zone_df[zone_df['BatterLR'] == selected_lr]

        if zone_df.empty:
            st.info("選択した条件（打者の左右）のデータがありません。")
        else:
            col1, col2 = st.columns(2)
            
            with col1:
                st.markdown(f"**コース別 {label_s} / 見逃し率(※)**<br><small>※選択中のデータ数: {len(zone_df)}球</small>", unsafe_allow_html=True)
                zone_texts = []
                xs, ys = [], []
                
                for z in [1,2,3,4,5,6,7,8,9, 11,12,13,14]:
                    # 🌟 フィルタリング済みの zone_df を使用
                    z_data = zone_df[zone_df['PitchLocation'] == z]
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
    
                fig_zone1 = go.Figure(go.Scatter(x=xs, y=ys, mode="text", text=zone_texts, textfont=dict(size=12, color="black")))
                fig_zone1.update_layout(
                    xaxis=dict(range=[-1, 5], showticklabels=False, showgrid=False, zeroline=False),
                    yaxis=dict(range=[-1, 5], showticklabels=False, showgrid=False, zeroline=False),
                    width=350, height=350, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="whitesmoke",
                    shapes=board_shapes
                )
                st.plotly_chart(fig_zone1, use_container_width=True)
    
            with col2:
                st.markdown("**コース別 ゴロ / フライ / ライナー 発生率**")
                hit_texts = []
                h_xs, h_ys = [], []
                
                for z in [1,2,3,4,5,6,7,8,9, 11,12,13,14]:
                    # 🌟 フィルタリング済みの zone_df を使用
                    z_data = zone_df[(zone_df['PitchLocation'] == z) & (zone_df['HitType'].notna())]
                    prefix = f"<b>{zone_names[z]}</b><br>" if z in zone_names else ""
                    
                    if not z_data.empty:
                        _goro = pct((z_data['HitType'] == 'ゴロ').sum(), len(z_data))
                        _fly = pct((z_data['HitType'] == 'フライ').sum(), len(z_data))
                        _liner = pct((z_data['HitType'] == 'ライナー').sum(), len(z_data))
                        txt = f"{prefix}ゴ:{_goro:.0f}%<br>フ:{_fly:.0f}%<br>ラ:{_liner:.0f}%"
                    else:
                        txt = f"{prefix}-"
                    
                    x, y = zone_map[z]
                    h_xs.append(x)
                    h_ys.append(y)
                    hit_texts.append(txt)
    
                fig_zone2 = go.Figure(go.Scatter(x=h_xs, y=h_ys, mode="text", text=hit_texts, textfont=dict(size=11, color="black")))
                fig_zone2.update_layout(
                    xaxis=dict(range=[-1, 5], showticklabels=False, showgrid=False, zeroline=False),
                    yaxis=dict(range=[-1, 5], showticklabels=False, showgrid=False, zeroline=False),
                    width=350, height=350, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="whitesmoke",
                    shapes=board_shapes
                )
                st.plotly_chart(fig_zone2, use_container_width=True)

        with st.expander("データログ"):
            cols = ['Date', 'Inning', 'Batter', 'BatterLR', 'Pitcher', 'PitchResult', 'HitResult', 'HitType', 'Memo']
            st.dataframe(target_df[[c for c in cols if c in df.columns]].fillna('').sort_values('Date'))

with tab2:
    chart_df = target_df.dropna(subset=['打球X', '打球Y'])
    
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

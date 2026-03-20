import streamlit as st
import pandas as pd
import requests
import io
import math
import random
import plotly.graph_objects as go
import base64

# --- ⚙️ 設定エリア ---
GITHUB_USER = "Yuto02-10"   
GITHUB_REPO = "Match--Metrics"  
GITHUB_FOLDER = "試合データ"      
GITHUB_IMAGE = "打球分析.png"    
GITHUB_TOKEN = None             

# --- アプリ設定 ---
st.set_page_config(page_title="チームデータ分析", layout="wide")
st.title("⚾️ チームデータ統合システム")

# --- 🌟 ユーティリティ関数（これらが定義されていないとNameErrorになります） ---

def pct(n, d):
    """割合を計算する関数"""
    return (n / d * 100) if d > 0 else 0

def read_csv_robust(file_bytes):
    """ExcelのShift-JISと標準のUTF-8両方に対応する読み込み関数"""
    try:
        return pd.read_csv(io.BytesIO(file_bytes), encoding='utf-8')
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(file_bytes), encoding='cp932')

# --- 1. データ取得関数 ---
@st.cache_data(ttl=600, show_spinner=False)
def fetch_github_data(user, repo, folder, token=None):
    base_url = f"https://api.github.com/repos/{user}/{repo}/contents"
    if folder: base_url += f"/{folder}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token: headers["Authorization"] = f"token {token}"
    
    try:
        response = requests.get(base_url, headers=headers)
        if response.status_code == 403:
            return pd.DataFrame(), "GitHubのアクセス制限中です(403)。左のボタンから直接CSVをアップロードしてください。"
        if response.status_code != 200:
            return pd.DataFrame(), f"Githubアクセスエラー({response.status_code})"
        
        files = response.json()
        csv_files = [f for f in files if isinstance(f, dict) and f.get('name', '').lower().endswith('.csv')]
        
        df_list = []
        for f in csv_files:
            if f.get('download_url'):
                r = requests.get(f['download_url'], headers=headers)
                temp = read_csv_robust(r.content)
                temp['SourceFile'] = f['name']
                df_list.append(temp)
        
        if df_list:
            return pd.concat(df_list, ignore_index=True), None
        return pd.DataFrame(), "CSVが見つかりません"
    except Exception as e:
        return pd.DataFrame(), f"通信エラー: {str(e)}"

# --- 2. 画像取得関数 ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_image(user, repo, filename, token=None):
    raw_url = f"https://raw.githubusercontent.com/{user}/{repo}/master/{filename}"
    try:
        r = requests.get(raw_url)
        if r.status_code == 200:
            b64_img = base64.b64encode(r.content).decode()
            return f"data:image/png;base64,{b64_img}", None
    except: pass
    return None, "画像なし"

# --- 3. データ前処理 ---
def clean_and_process(df):
    if df.empty: return df
    
    df.columns = df.columns.astype(str).str.strip().str.replace('　', '').str.replace('\n', '')
    df = df.loc[:, ~df.columns.duplicated(keep='first')].copy()
    
    # 列名の対応
    column_mapping = {
        'イニング': 'Inning', 'ボール': 'Ball', 'ストライク': 'Strike',
        '投手': 'Pitcher', '打者': 'Batter', '球種': 'PitchType',
        '投球位置': 'PitchLocation', '投球結果': 'PitchResult',
        '三振四球': 'KorBB', '打撃結果': 'HitResult', '打球タイプ': 'HitType',
        'メモ': 'Memo', '日付': 'Date', 'Ｄａｔｅ': 'Date', 'date': 'Date',
        'プレーアウト数': 'PlayOuts'
    }
    df = df.rename(columns=column_mapping)
    df = df.loc[:, ~df.columns.duplicated(keep='first')].copy()

    required = ['PitchLocation', 'PitchResult', 'HitResult', 'HitType', 'KorBB', 'Memo', 'Batter', 'Pitcher', 'Date', 'Ball', 'Strike', 'PlayOuts', 'SourceFile']
    for col in required:
        if col not in df.columns: df[col] = None

    # 選手名の空白除去
    for col in ['Batter', 'Pitcher']:
        df[col] = df[col].astype(str).str.replace(r'\s+', '', regex=True).replace('nan', None)
    
    # 日付のオートフィル（1行目だけ入っている場合に対応）
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    if 'SourceFile' in df.columns:
        df['Date'] = df.groupby('SourceFile')['Date'].transform(lambda x: x.ffill().bfill())

    # 判定フラグの作成
    def check_result(val, keywords):
        if not isinstance(val, str): return False
        return any(k in val for k in keywords)

    df['is_Swing'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振', 'ファール', 'ファウル', 'インプレー']))
    df['is_Miss'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振']))
    df['is_Zone'] = pd.to_numeric(df['PitchLocation'], errors='coerce').isin(range(1, 10))
    df['PlayOuts'] = pd.to_numeric(df['PlayOuts'], errors='coerce').fillna(0)

    # 打球座標（Memoから変換）
    def parse_xy(memo):
        rank_to_dist = {1: 10, 2: 65, 3: 110, 4: 155, 5: 195, 6: 240, 7: 290}
        dir_to_angle = {'B': -46.5, 'C': -42.2, 'D': -38, 'E': -34.2, 'F': -30, 'G': -26, 'H': -22.15,'I': -18, 'J': -14, 'K': -10, 'L': -6, 'M': -2.5, 'N': 1.5, 'O': 5.5, 'P': 9.5, 'Q': 13.5, 'R': 17.5, 'S': 21.5, 'T': 25.5, 'U': 29.5, 'V': 33.5, 'W': 37.5, 'X': 41.5, 'Y': 45.5}
        if not isinstance(memo, str) or len(memo) < 2: return pd.Series([None, None])
        try:
            memo = memo.replace(" ", "").upper()
            d, r_s = memo[0], "".join([c for c in memo[1:] if c.isdigit()])
            if not r_s: return pd.Series([None, None])
            dist = rank_to_dist.get(int(r_s), 0)
            angle = dir_to_angle.get(d)
            if angle is not None and dist > 0:
                rad = math.radians(angle)
                return pd.Series([round(dist*1.2*math.sin(rad),2), round(dist*0.8*math.cos(rad),2)])
        except: pass
        return pd.Series([None, None])

    df[['打球X', '打球Y']] = df['Memo'].apply(parse_xy)
    return df

# --- 4. メイン処理 ---

# サイドバー設定
st.sidebar.header("📁 データ読み込み")
if st.sidebar.button("🔄 最新の情報に更新"):
    st.cache_data.clear()
    st.rerun()

# GitHubから取得
df_github, err = fetch_github_data(GITHUB_USER, GITHUB_REPO, GITHUB_FOLDER, GITHUB_TOKEN)
if err: st.sidebar.warning(err)

# 手動アップロード
uploaded = st.sidebar.file_uploader("📂 直接CSVをアップロード", accept_multiple_files=True)
df_local = pd.DataFrame()
if uploaded:
    df_local = pd.concat([read_csv_robust(f.read()).assign(SourceFile=f.name) for f in uploaded], ignore_index=True)

# 結合と前処理
df = pd.concat([df_github, df_local], ignore_index=True)
if df.empty:
    st.info("データがありません。GitHubの確認、またはCSVをアップロードしてください。")
    st.stop()

df = clean_and_process(df)

# 期間選択
valid_dates = df['Date'].dropna()
if not valid_dates.empty:
    min_d, max_d = valid_dates.min().date(), valid_dates.max().date()
    start_d, end_d = st.sidebar.date_input("📅 分析期間", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    df = df[(df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d)]

# 分析対象の選択
mode = st.sidebar.radio("🔍 モード選択", ["👤 打者分析", "⚾ 投手分析"])
player_col = 'Batter' if mode == "👤 打者分析" else 'Pitcher'
players = sorted(df[player_col].dropna().unique())
selected_player = st.sidebar.selectbox("選手を選択", players)
target_df = df[df[player_col] == selected_player]

# 結果表示
st.header(f"{selected_player} 選手の分析結果")
tab1, tab2 = st.tabs(["📊 成績・グラフ", "🏟 打球方向"])

with tab1:
    if target_df.empty:
        st.warning("データなし")
    else:
        # 指標計算
        pa = len(target_df[(target_df['HitResult'].notna()) | (target_df['KorBB'].notna()) | (target_df['PitchResult'].str.contains('死球', na=False))])
        hits = target_df['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打', '安打']).sum()
        bb = target_df['KorBB'].astype(str).str.contains('四球').sum()
        hbp = target_df['PitchResult'].astype(str).str.contains('死球').sum()
        so = target_df['KorBB'].astype(str).str.contains('三振').sum()
        sac = target_df['HitResult'].isin(['犠打', '犠飛']).sum()
        ab = pa - bb - hbp - sac
        
        if mode == "👤 打者分析":
            stats = {"打席": pa, "打率": f"{hits/ab:.3f}" if ab > 0 else ".000", "四球率": f"{pct(bb, pa):.1f}%", "三振率": f"{pct(so, pa):.1f}%"}
        else:
            outs = target_df['PlayOuts'].sum()
            stats = {"イニング": f"{int(outs//3)}.{int(outs%3)}", "K%": f"{pct(so, pa):.1f}%", "BB%": f"{pct(bb, pa):.1f}%"}
        
        st.table(pd.DataFrame([stats]))

        # カウント別グラフ
        c_df = target_df.copy()
        c_df['Count'] = c_df['Ball'].astype(str) + "-" + c_df['Strike'].astype(str)
        c_data = []
        for c in sorted(c_df['Count'].unique()):
            tmp = c_df[c_df['Count'] == c]
            z_tmp = tmp[tmp['is_Zone']]
            c_data.append({"Count": c, "スイング率": pct(tmp['is_Swing'].sum(), len(tmp)), "ゾーン内見逃率": pct(len(z_tmp) - z_tmp['is_Swing'].sum(), len(z_tmp))})
        
        fig = go.Figure()
        fig.add_trace(go.Bar(x=[d['Count'] for d in c_data], y=[d['スイング率'] for d in c_data], name='スイング率'))
        fig.add_trace(go.Bar(x=[d['Count'] for d in c_data], y=[d['ゾーン内見逃率'] for d in c_data], name='ゾーン見逃し'))
        fig.update_layout(barmode='group', yaxis_title="割合(%)")
        st.plotly_chart(fig, use_container_width=True)

with tab2:
    bg_img, _ = fetch_github_image(GITHUB_USER, GITHUB_REPO, GITHUB_IMAGE)
    chart_df = target_df.dropna(subset=['打球X', '打球Y'])
    if chart_df.empty:
        st.info("打球データなし")
    else:
        fig_map = go.Figure(go.Scatter(x=chart_df['打球X'], y=chart_df['打球Y'], mode='markers', text=chart_df['Memo']))
        if bg_img:
            fig_map.add_layout_image(dict(source=bg_img, xref="x", yref="y", x=-292.5, y=296.25, sizex=585, sizey=315, sizing="stretch", layer="below"))
        fig_map.update_layout(width=600, height=600, xaxis_range=[-200, 200], yaxis_range=[-20, 240])
        st.plotly_chart(fig_map)

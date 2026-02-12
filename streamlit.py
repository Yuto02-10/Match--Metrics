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
st.title("⚾️ チームデータ統合システム (期間選択対応)")

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

# --- 3. データ前処理 (日付対応) ---
def clean_and_process(df):
    if df.empty: return df
    
    # 1. カラム名の空白削除
    df.columns = df.columns.str.strip()
    
    # 2. 必須カラムの存在保証 (Dateを追加)
    required = ['PitchLocation', 'PitchResult', 'HitResult', 'KorBB', 'Memo', 'Batter', 'Pitcher', 'Date']
    for col in required:
        if col not in df.columns: df[col] = None
    
    # 3. 日付変換 (New!)
    # エラーがあっても強制的に変換 (変換できないものはNaTになる)
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    
    # 4. 文字列データのクリーニング
    str_cols = df.select_dtypes(include=['object']).columns
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()
        df.loc[df[col] == 'nan', col] = None

    # 5. 数値変換
    df['PitchLocation'] = pd.to_numeric(df['PitchLocation'], errors='coerce')
    
    # 6. フラグ立て
    df['is_Zone'] = df['PitchLocation'].isin(range(1, 10))
    
    def check_result(val, keywords):
        if not isinstance(val, str): return False
        return any(k in val for k in keywords)

    df['is_Swing'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振', 'ファール', 'インプレー']))
    df['is_Miss'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振']))
    df['is_Contact'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['ファール', 'インプレー']))

    # 7. 座標変換
    def parse_xy(memo):
        rank_to_dist = {1: 10, 2: 65, 3: 110, 4: 155, 5: 195, 6: 240, 7: 290}
        dir_to_angle = {
            'B': -46.5, 'C': -42.2, 'D': -38, 'E': -34.2, 'F': -30, 'G': -26,
            'H': -22.15,'I': -18, 'J': -14, 'K': -10, 'L': -6, 'M': -2.5,
            'N': 1.5, 'O': 5.5, 'P': 9.5, 'Q': 13.5, 'R': 17.5, 'S': 21.5,
            'T': 25.5, 'U': 29.5, 'V': 33.5, 'W': 37.5, 'X': 41.5, 'Y': 45.5
        }
        
        if not isinstance(memo, str) or len(memo) < 2:
            return pd.Series([None, None])
            
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

# データ処理
df = clean_and_process(df)

# --- 📅 期間選択機能 (ここを追加) ---
st.sidebar.markdown("---")
st.sidebar.header("📅 期間設定")

# 日付データが有効かチェック
valid_dates = df['Date'].dropna()

if not valid_dates.empty:
    min_date = valid_dates.min().date()
    max_date = valid_dates.max().date()
    
    # 期間選択スライダー
    start_date, end_date = st.sidebar.date_input(
        "分析期間を選択",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )
    
    # データをフィルタリング
    # Date列がNaT(日付なし)のデータは除外されます
    mask = (df['Date'].dt.date >= start_date) & (df['Date'].dt.date <= end_date)
    df_filtered = df.loc[mask]
    
    st.sidebar.success(f"期間: {start_date} ～ {end_date}")
    st.sidebar.info(f"対象データ: {len(df_filtered)} 行 (全 {len(df)} 行中)")
    
    # 以降はフィルタリングされたデータ(df_filtered)を使用
    df = df_filtered

else:
    st.sidebar.warning("CSVに有効な 'Date' 列が見つかりません。全期間を表示します。")


# 画像取得
bg_image, img_err = fetch_github_image(GITHUB_USER, GITHUB_REPO, GITHUB_IMAGE, GITHUB_TOKEN)

# --- 分析画面 ---
players = sorted(list(set(df['Batter'].dropna().unique()) | set(df['Pitcher'].dropna().unique())))

if not players:
    st.warning("選択された期間に該当する選手データがありません。期間を広げてください。")
    st.stop()

selected_player = st.selectbox("選手を選択", players)
b_df = df[df['Batter'] == selected_player]

tab1, tab2 = st.tabs(["📊 成績表", "🏟 打球方向"])

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
        
        swings = b_df['is_Swing'].sum()
        contact_cnt = b_df['is_Contact'].sum()
        
        misses = b_df['is_Miss'].sum()
        
        # Zone系
        z_df = b_df[b_df['is_Zone']]
        z_swings = z_df['is_Swing'].sum()
        z_contact = z_df['is_Contact'].sum()
        
        # Out系
        o_df = b_df[~b_df['is_Zone']]
        o_swings = o_df['is_Swing'].sum()
        o_contact = o_df['is_Contact'].sum()

        def pct(n, d): return (n / d * 100) if d > 0 else 0
        
        stats = {
            "試合数": b_df['Date












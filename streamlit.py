import streamlit as st
import pandas as pd
import requests
import io
import math
import random
import plotly.graph_objects as go
import base64

# --- ⚙️ 設定エリア ---
# ここをあなたのGitHub情報に書き換えてください
GITHUB_USER = "Yuto02-10"   
GITHUB_REPO = "Match--Metrics"  
GITHUB_FOLDER = "試合データ"      
GITHUB_IMAGE = "打球分析.png"    
GITHUB_TOKEN = None             

# --- アプリ設定 ---
st.set_page_config(page_title="チームデータ分析", layout="wide")
st.title("⚾️ チームデータ統合システム (GitHub連携復旧版)")

# --- 文字コード自動判定関数 ---
def read_csv_robust(file_bytes):
    try:
        return pd.read_csv(io.BytesIO(file_bytes), encoding='utf-8')
    except UnicodeDecodeError:
        return pd.read_csv(io.BytesIO(file_bytes), encoding='cp932')

# --- 1. データ取得関数 ---
@st.cache_data(ttl=600, show_spinner=False) # 10分ごとに更新
def fetch_github_data(user, repo, folder, token=None):
    base_url = f"https://api.github.com/repos/{user}/{repo}/contents"
    if folder: base_url += f"/{folder}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token: headers["Authorization"] = f"token {token}"
    
    try:
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            return pd.DataFrame(), f"Githubアクセスエラー({response.status_code}): 設定を確認してください"
        
        files = response.json()
        if not isinstance(files, list):
            return pd.DataFrame(), "フォルダが見つからないか、ファイル形式が不正です"

        csv_files = [f for f in files if isinstance(f, dict) and f.get('name', '').lower().endswith('.csv')]
        if not csv_files: 
            return pd.DataFrame(), f"フォルダ「{folder}」内にCSVファイルが見つかりません"

        df_list = []
        for f in csv_files:
            if f.get('download_url'):
                r = requests.get(f['download_url'], headers=headers)
                temp = read_csv_robust(r.content)
                temp['SourceFile'] = f['name']
                df_list.append(temp)
        
        if df_list:
            combined = pd.concat(df_list, ignore_index=True)
            return combined, None
        return pd.DataFrame(), "CSVの読み込みに失敗しました"
    except Exception as e:
        return pd.DataFrame(), f"通信エラー: {str(e)}"

# --- 3. データ前処理 ---
def clean_and_process(df):
    if df.empty: return df
    
    # カラム名のクリーニング（全角・改行・空白削除）
    df.columns = df.columns.astype(str).str.strip().str.replace('　', '').str.replace('\n', '')
    
    # 重複カラムを削除（変換前に一度リセット）
    df = df.loc[:, ~df.columns.duplicated(keep='first')].copy()
    
    # 🌟 新旧カラム名マッピング
    column_mapping = {
        'イニング': 'Inning', 'ボール': 'Ball', 'ストライク': 'Strike',
        '投手': 'Pitcher', '打者': 'Batter', '球種': 'PitchType',
        '投球位置': 'PitchLocation', '投球結果': 'PitchResult',
        '三振四球': 'KorBB', '打撃結果': 'HitResult', '打球タイプ': 'HitType',
        'メモ': 'Memo', '日付': 'Date', 'Ｄａｔｅ': 'Date', 'date': 'Date',
        'プレーアウト数': 'PlayOuts'
    }
    df = df.rename(columns=column_mapping)
    
    # 🌟 変換後に「Date」が重複した場合も統合
    df = df.loc[:, ~df.columns.duplicated(keep='first')].copy()

    # 必須列の確保
    required = ['PitchLocation', 'PitchResult', 'HitResult', 'HitType', 'KorBB', 'Memo', 'Batter', 'Pitcher', 'Date', 'Ball', 'Strike', 'PlayOuts', 'SourceFile']
    for col in required:
        if col not in df.columns: df[col] = None

    # 選手名の空白除去
    for col in ['Batter', 'Pitcher']:
        df[col] = df[col].astype(str).str.replace(r'\s+', '', regex=True).replace('nan', None)
    
    # 日付処理：1行目のみの入力でも全行に適用（オートフィル）
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    if 'SourceFile' in df.columns:
        df['Date'] = df.groupby('SourceFile')['Date'].transform(lambda x: x.ffill().bfill())

    # 文字列データのクリーンアップ
    str_cols = ['PitchResult', 'HitResult', 'HitType', 'KorBB', 'Memo']
    for col in str_cols:
        df[col] = df[col].astype(str).str.strip()
        df.loc[df[col].isin(['nan', 'None', '', '-', '不明']), col] = None

    # 数値変換
    df['PitchLocation'] = pd.to_numeric(df['PitchLocation'], errors='coerce')
    df['is_Zone'] = df['PitchLocation'].apply(lambda x: int(x) in range(1, 10) if pd.notnull(x) else False)
    df['PlayOuts'] = pd.to_numeric(df['PlayOuts'], errors='coerce').fillna(0)
    
    # 判定ロジック
    def check_result(val, keywords):
        if not isinstance(val, str): return False
        return any(k in val for k in keywords)

    df['is_Swing'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振', 'ファール', 'ファウル', 'インプレー']))
    df['is_Miss'] = df['PitchResult'].apply(lambda x: check_result(str(x), ['空振']))

    # 打球座標解析
    def parse_xy(memo):
        rank_to_dist = {1: 10, 2: 65, 3: 110, 4: 155, 5: 195, 6: 240, 7: 290}
        dir_to_angle = {'B': -46.5, 'C': -42.2, 'D': -38, 'E': -34.2, 'F': -30, 'G': -26, 'H': -22.15,'I': -18, 'J': -14, 'K': -10, 'L': -6, 'M': -2.5, 'N': 1.5, 'O': 5.5, 'P': 9.5, 'Q': 13.5, 'R': 17.5, 'S': 21.5, 'T': 25.5, 'U': 29.5, 'V': 33.5, 'W': 37.5, 'X': 41.5, 'Y': 45.5}
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
st.sidebar.header("📁 データ更新")
if st.sidebar.button("🔄 GitHubから最新データを取得"):
    st.cache_data.clear()
    st.rerun()

# データ読み込み
df_github, err = fetch_github_data(GITHUB_USER, GITHUB_REPO, GITHUB_FOLDER, GITHUB_TOKEN)
if err: st.sidebar.error(err)

# 手動アップロード枠
uploaded = st.sidebar.file_uploader("📂 またはCSVを直接アップロード", accept_multiple_files=True)
df_local = pd.DataFrame()
if uploaded:
    local_dfs = [read_csv_robust(f.read()).assign(SourceFile=f.name) for f in uploaded]
    df_local = pd.concat(local_dfs, ignore_index=True)

# 結合
if not df_local.empty:
    df = pd.concat([df_github, df_local], ignore_index=True) if not df_github.empty else df_local
else:
    df = df_github

if df.empty:
    st.warning("表示するデータがありません。GitHubのフォルダ名やCSVファイルを確認してください。")
    st.stop()

df = clean_and_process(df)

# デバッグ用情報（不要なら削除OK）
with st.expander("🛠 読み込みデバッグ情報"):
    st.write(f"取得ファイル数: {df['SourceFile'].nunique()}")
    st.write("認識された列:", list(df.columns))
    st.dataframe(df.head(5))

# --- 期間フィルター ---
valid_dates = df['Date'].dropna()
if not valid_dates.empty:
    min_d, max_d = valid_dates.min().date(), valid_dates.max().date()
    start_d, end_d = st.sidebar.date_input("📅 分析期間", value=(min_d, max_d), min_value=min_d, max_value=max_d)
    df = df[(df['Date'].dt.date >= start_d) & (df['Date'].dt.date <= end_d)]

# --- 分析モード ---
mode = st.sidebar.radio("🔍 モード", ["👤 打者分析", "⚾ 投手分析"])
players = sorted(df['Batter' if mode == "👤 打者分析" else 'Pitcher'].dropna().unique())
selected = st.sidebar.selectbox("選手選択", players)
target_df = df[df['Batter' if mode == "👤 打者分析" else 'Pitcher'] == selected]

# 以降、成績計算・グラフ表示（前回のロジックを継承）
st.subheader(f"{selected} 選手の分析結果")
# (ここに前回の表・グラフ表示コードを続けてください)

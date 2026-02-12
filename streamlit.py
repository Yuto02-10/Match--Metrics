import streamlit as st
import pandas as pd
import requests
import io
import math
import random
import plotly.graph_objects as go

# --- ⚙️ 設定エリア ---
GITHUB_USER = "Yuto-0210"   # ユーザー名
GITHUB_REPO = "Match--Metrics"  # リポジトリ名
GITHUB_FOLDER = "試合データ"      # フォルダ名
GITHUB_IMAGE = "打球分析.png"    # 画像ファイル名
# Privateリポジトリの場合はここにトークンを入力 (PublicならNoneのまま)
GITHUB_TOKEN = None 

# --- アプリ設定 ---
st.set_page_config(page_title="チームデータ分析", layout="wide")
st.title("⚾️ チームデータ統合システム")

# --- 関数: Githubデータ取得 (デバッグ機能強化版) ---
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_github_data(user, repo, folder, token=None):
    base_url = f"https://api.github.com/repos/{user}/{repo}/contents"
    if folder: base_url += f"/{folder}"
    
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    try:
        # 1. ファイル一覧取得
        response = requests.get(base_url, headers=headers)
        if response.status_code != 200:
            return pd.DataFrame(), f"Githubアクセスエラー (Status: {response.status_code})"
        
        files = response.json()
        csv_files = [f for f in files if isinstance(f, dict) and f.get('name', '').endswith('.csv')]
        
        if not csv_files:
            return pd.DataFrame(), "CSVファイルが見つかりません"

        # 2. CSV読み込み
        df_list = []
        for f in csv_files:
            if f.get('download_url'):
                r = requests.get(f['download_url'], headers=headers) # headersを追加
                temp = pd.read_csv(io.BytesIO(r.content))
                temp['SourceFile'] = f['name']
                df_list.append(temp)
        
        if df_list:
            combined = pd.concat(df_list, ignore_index=True)
            return combined, None
        return pd.DataFrame(), "データ結合失敗"

    except Exception as e:
        return pd.DataFrame(), f"プログラムエラー: {e}"

# --- 関数: 指標計算のための前処理 ---
def preprocess_data(df):
    if df.empty: return df
    
    # 必須カラムの確認と作成
    required_cols = ['PitchLocation', 'PitchResult', 'HitResult', 'KorBB']
    for col in required_cols:
        if col not in df.columns:
            df[col] = None # ない場合は空の列を作る
            
    # ストライクゾーン定義 (1-9)
    # PitchLocationが数値型でない場合に備えて変換
    df['PitchLocation'] = pd.to_numeric(df['PitchLocation'], errors='coerce')
    df['is_Zone'] = df['PitchLocation'].isin(range(1, 10))
    
    # スイング・コンタクト判定
    df['is_Swing'] = df['PitchResult'].isin(['空振', 'ファール', 'インプレー'])
    df['is_Miss'] = df['PitchResult'] == '空振'
    df['is_Contact'] = df['PitchResult'].isin(['ファール', 'インプレー'])
    
    return df

# --- 関数: Memo座標変換 ---
def parse_memo_to_xy(memo):
    # (省略せずに前回のロジックを維持)
    rank_to_dist = {1: 10, 2: 65, 3: 110, 4: 155, 5: 195, 6: 240, 7: 290}
    dir_to_angle = {
        'B': -46.5, 'C': -42.2, 'D': -38, 'E': -34.2, 'F': -30, 'G': -26,
        'H': -22.15,'I': -18, 'J': -14, 'K': -10, 'L': -6, 'M': -2.5,
        'N': 1.5, 'O': 5.5, 'P': 9.5, 'Q': 13.5, 'R': 17.5, 'S': 21.5,
        'T': 25.5, 'U': 29.5, 'V': 33.5, 'W': 37.5, 'X': 41.5, 'Y': 45.5
    }
    if isinstance(memo, str) and len(memo) >= 2:
        d = memo[0].upper()
        try:
            rank = int(memo[1])
            angle = dir_to_angle.get(d)
            if angle is not None and rank in rank_to_dist:
                angle += random.uniform(-0.05, 0.05)
                dist = rank_to_dist[rank] * random.uniform(0.9, 1.1)
                rad = math.radians(angle)
                return pd.Series([round(dist*1.2*math.sin(rad),2), round(dist*0.8*math.cos(rad),2)])
        except: pass
    return pd.Series([None, None])


# --- メイン処理 ---
with st.spinner("データを読み込んでいます..."):
    # データ取得
    df, err_msg = fetch_github_data(GITHUB_USER, GITHUB_REPO, GITHUB_FOLDER, GITHUB_TOKEN)

if not df.empty:
    st.sidebar.success(f"✅ 読み込み成功: {len(df)} 行")
    df = preprocess_data(df)
    
    # 座標変換
    if 'Memo' in df.columns:
        df[['打球X', '打球Y']] = df['Memo'].apply(parse_memo_to_xy)
    else:
        df['打球X'], df['打球Y'] = None, None
        
else:
    st.error(f"⚠️ データ読み込み失敗: {err_msg}")
    st.info("サイドバーから手動でCSVをアップロードしてください。")
    uploaded = st.sidebar.file_uploader("手動アップロード", accept_multiple_files=True)
    if uploaded:
        df = pd.concat([pd.read_csv(f).assign(SourceFile=f.name) for f in uploaded], ignore_index=True)
        df = preprocess_data(df)
        if 'Memo' in df.columns:
            df[['打球X', '打球Y']] = df['Memo'].apply(parse_memo_to_xy)
    else:
        st.stop()

# --- 分析画面 ---
st.sidebar.markdown("---")
players = sorted(list(set(df['Batter'].dropna().unique()) | set(df['Pitcher'].dropna().unique())))
selected_player = st.sidebar.selectbox("選手を選択", players)

tab1, tab2 = st.tabs(["📊 詳細成績", "🏟 打球方向"])

# --- タブ1: 指標表の表示 ---
with tab1:
    b_df = df[df['Batter'] == selected_player]
    
    if b_df.empty:
        st.warning("この選手の打撃データはありません。")
    else:
        # 指標計算
        pa_rows = b_df[(b_df['KorBB'].notna()) | (b_df['HitResult'].notna())]
        pa = len(pa_rows)
        hits = b_df['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打']).sum()
        bb = b_df['KorBB'].isin(['四球']).sum()
        hbp = b_df['PitchResult'].isin(['死球']).sum()
        sac = b_df['HitResult'].isin(['犠打', '犠飛']).sum()
        ab = pa - bb - hbp - sac
        so = b_df['KorBB'].astype(str).str.contains('三振').sum()

        # Advanced Stats
        swings = b_df['is_Swing'].sum()
        misses = b_df['is_Miss'].sum()
        
        # Zone系
        z_df = b_df[b_df['is_Zone']]
        z_swings = z_df['is_Swing'].sum()
        z_contacts = z_df['is_Contact'].sum()
        
        # Out系
        o_df = b_df[~b_df['is_Zone']]
        o_swings = o_df['is_Swing'].sum()
        o_contacts = o_df['is_Contact'].sum()

        def pct(n, d): return (n/d*100) if d>0 else 0
        
        # 表示用辞書作成
        stats = {
            "試合数": b_df['SourceFile'].nunique(),
            "打席数": pa,
            "打率": f"{hits/ab:.3f}" if ab>0 else ".000",
            "四球率": f"{pct(bb, pa):.1f}%",
            "三振率": f"{pct(so, pa):.1f}%",
            "O-Swing%": f"{pct(o_swings, len(o_df)):.1f}%",
            "Z-Swing%": f"{pct(z_swings, len(z_df)):.1f}%",
            "SwStr%": f"{pct(misses, len(b_df)):.1f}%",
            "O-Contact%": f"{pct(o_contacts, o_swings):.1f}%",
            "Z-Contact%": f"{pct(z_contacts, z_swings):.1f}%",
            "Contact%": f"{pct(b_df['is_Contact'].sum(), swings):.1f}%",
            "K-BB%": f"{pct(so-bb, pa):.1f}%"
        }
        
        st.subheader("打撃成績サマリー")
        # データフレームにして表示（ここが表示されていなかったはず）
        st.dataframe(pd.DataFrame([stats]), use_container_width=True)
        
        with st.expander("全打席ログを確認"):
            st.dataframe(b_df)

# --- タブ2: 打球方向 ---
with tab2:
    chart_df = df[df['Batter'] == selected_player].copy()
    chart_df = chart_df.dropna(subset=['打球X', '打球Y'])
    
    if chart_df.empty:
        st.info("打球座標データがありません。")
    else:
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=chart_df['打球X'], y=chart_df['打球Y'],
            mode='markers',
            marker=dict(size=10, color='blue'),
            text=chart_df['Memo'],
            name=selected_player
        ))
        fig.update_layout(
            xaxis=dict(range=[-200, 200], showticklabels=False),
            yaxis=dict(range=[-20, 240], showticklabels=False),
            width=600, height=600,
            plot_bgcolor="white"
        )
        st.plotly_chart(fig)





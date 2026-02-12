import streamlit as st
import pandas as pd
import requests
import io

# --- 設定 ---
st.set_page_config(page_title="野球データ分析 (GitHub連携)", layout="wide")
st.title("⚾️ 野球データ詳細分析（GitHub連携版）")

# --- 関数: データの結合と前処理 ---
def process_data(df_list):
    if not df_list:
        return pd.DataFrame()
    
    combined = pd.concat(df_list, ignore_index=True)
    
    # ストライクゾーン定義 (1-9をゾーン内)
    strike_zones = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    combined['is_Zone'] = combined['PitchLocation'].isin(strike_zones)
    
    # スイング判定 (空振, ファール, インプレー)
    swing_results = ['空振', 'ファール', 'インプレー']
    combined['is_Swing'] = combined['PitchResult'].isin(swing_results)
    
    # コンタクト判定 (ファール, インプレー)
    contact_results = ['ファール', 'インプレー']
    combined['is_Contact'] = combined['PitchResult'].isin(contact_results)
    
    # 空振り判定
    miss_results = ['空振']
    combined['is_Miss'] = combined['PitchResult'].isin(miss_results)

    return combined

# --- 関数: GitHubからファイルを取得 ---
@st.cache_data(ttl=600) # 10分間キャッシュ
def load_from_github(owner, repo, folder):
    # GitHub APIのエンドポイント
    api_url = f"https://api.github.com/repos/{owner}/{repo}/contents/{folder}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    
    try:
        response = requests.get(api_url, headers=headers)
        if response.status_code != 200:
            st.error(f"GitHubへのアクセスに失敗しました (Status: {response.status_code})。リポジトリ名やフォルダ名を確認してください。")
            return []
        
        files = response.json()
        csv_files = [f for f in files if f['name'].endswith('.csv')]
        
        df_list = []
        progress_bar = st.progress(0)
        
        for i, file_info in enumerate(csv_files):
            # 生データ(Raw)のURLから読み込む
            download_url = file_info['download_url']
            try:
                # 日本語ファイル名対応のため、contentを取得してdecode
                file_response = requests.get(download_url)
                file_content = file_response.content
                temp_df = pd.read_csv(io.BytesIO(file_content))
                temp_df['SourceFile'] = file_info['name'] # ファイル名を記録
                df_list.append(temp_df)
            except Exception as e:
                st.warning(f"{file_info['name']} の読み込みをスキップしました: {e}")
            
            # 進捗バー更新
            progress_bar.progress((i + 1) / len(csv_files))
            
        progress_bar.empty()
        return df_list

    except Exception as e:
        st.error(f"エラーが発生しました: {e}")
        return []

# --- 1. データソース選択 (サイドバー) ---
st.sidebar.header("📁 データソース選択")
data_source = st.sidebar.radio("取得方法", ["CSVファイルをアップロード", "GitHubから取得"])

df = pd.DataFrame()

if data_source == "CSVファイルをアップロード":
    uploaded_files = st.sidebar.file_uploader("CSVをドラッグ＆ドロップ", type="csv", accept_multiple_files=True)
    if uploaded_files:
        df_list = []
        for file in uploaded_files:
            try:
                t_df = pd.read_csv(file)
                t_df['SourceFile'] = file.name
                df_list.append(t_df)
            except:
                pass
        df = process_data(df_list)

elif data_source == "GitHubから取得":
    st.sidebar.markdown("---")
    # 入力フォーム
    gh_owner = st.sidebar.text_input("ユーザー名 (Owner)", placeholder="例: your_name")
    gh_repo = st.sidebar.text_input("リポジトリ名 (Repo)", placeholder="例: baseball_data")
    gh_folder = st.sidebar.text_input("フォルダ名 (Path)", value="試合データ")
    
    if st.sidebar.button("データを取得"):
        if gh_owner and gh_repo:
            with st.spinner('GitHubからデータを取得中...'):
                df_list = load_from_github(gh_owner, gh_repo, gh_folder)
                if df_list:
                    df = process_data(df_list)
                    st.sidebar.success(f"{len(df)} 件のデータを読み込みました！")
        else:
            st.sidebar.warning("ユーザー名とリポジトリ名を入力してください。")

# --- メイン処理 (データ読み込み完了後) ---
if df.empty:
    st.info("👈 サイドバーからデータを取り込んでください。")
    st.stop()

# --- 2. 選手選択と分析 ---
st.sidebar.markdown("---")
st.sidebar.header("🔍 選手検索")

# 選手リスト作成
all_players = sorted(list(set(df['Pitcher'].dropna()) | set(df['Batter'].dropna())))
if not all_players:
    st.error("有効な選手データが見つかりません。")
    st.stop()

selected_player = st.sidebar.selectbox("選手名を選択", all_players)

pitcher_df = df[df['Pitcher'] == selected_player]
batter_df = df[df['Batter'] == selected_player]

st.header(f"👤 {selected_player} 選手の詳細成績")

# タブ切り替え
tabs = []
if not pitcher_df.empty: tabs.append("投手成績")
if not batter_df.empty: tabs.append("打撃成績")

if not tabs:
    st.warning("データなし")
    st.stop()

current_tab = st.radio("表示", tabs, horizontal=True)
st.divider()

# --- 打撃成績 (詳細版) ---
if current_tab == "打撃成績":
    # 集計
    games = batter_df['SourceFile'].nunique()
    # 打席数(PA)
    pa_rows = batter_df[(batter_df['KorBB'].notna()) | (batter_df['HitResult'].notna())]
    pa = len(pa_rows)
    # 安打
    hits = batter_df['HitResult'].isin(['単打', '二塁打', '三塁打', '本塁打']).sum()
    # 四球
    bb = batter_df['KorBB'].isin(['四球']).sum()
    # 死球
    hbp = batter_df['PitchResult'].isin(['死球']).sum()
    # 犠打飛
    sac = batter_df['HitResult'].isin(['犠打', '犠飛']).sum()
    # 打数
    ab = pa - bb - hbp - sac
    # 三振
    so = batter_df['KorBB'].astype(str).str.contains('三振').sum()

    # セイバーメトリクス用集計
    total_p = len(batter_df)
    swings = batter_df['is_Swing'].sum()
    misses = batter_df['is_Miss'].sum()
    contacts = batter_df['is_Contact'].sum()
    
    # Zone
    z_df = batter_df[batter_df['is_Zone']]
    z_total = len(z_df)
    z_swings = z_df['is_Swing'].sum()
    z_contacts = z_df['is_Contact'].sum()
    
    # Out Zone
    o_df = batter_df[~batter_df['is_Zone']]
    o_total = len(o_df)
    o_swings = o_df['is_Swing'].sum()
    o_contacts = o_df['is_Contact'].sum()
    
    def pct(n, d): return (n/d*100) if d>0 else 0

    # データ作成
    stats_data = {
        "試合数": games,
        "打席数": pa,
        "打率": hits/ab if ab>0 else 0,
        "四球率": pct(bb, pa),
        "三振率": pct(so, pa),
        "O-Swing%": pct(o_swings, o_total),
        "Z-Swing%": pct(z_swings, z_total),
        "SwStr%": pct(misses, total_p),
        "O-Contact%": pct(o_contacts, o_swings),
        "Z-Contact%": pct(z_contacts, z_swings),
        "Contact%": pct(contacts, swings),
        "K-BB%": pct(so - bb, pa)
    }
    
    # フォーマット
    formatted = {k: (f"{v:.3f}" if "打率" in k else f"{v:.1f}%" if "%" in k or "率" in k else f"{v}") for k,v in stats_data.items()}
    
    st.subheader("📊 打撃成績 (Advanced)")
    st.dataframe(pd.DataFrame([formatted]), use_container_width=True)
    
    with st.expander("全打席ログ"):
        cols = ['SourceFile', 'Inning', 'Pitcher', 'PitchType', 'PitchLocation', 'PitchResult', 'HitResult']
        st.dataframe(batter_df[[c for c in cols if c in df.columns]], use_container_width=True)

# --- 投手成績 ---
elif current_tab == "投手成績":
    p_count = len(pitcher_df)
    k_count = pitcher_df['KorBB'].astype(str).str.contains('三振').sum()
    bb_count = pitcher_df['KorBB'].isin(['四球']).sum()
    
    st.subheader("📊 投手成績")
    c1, c2, c3 = st.columns(3)
    c1.metric("投球数", p_count)
    c2.metric("奪三振", k_count)
    c3.metric("与四球", bb_count)
    
    with st.expander("全投球ログ"):
        cols = ['SourceFile', 'Inning', 'Batter', 'PitchType', 'PitchLocation', 'PitchResult', 'HitResult']
        st.dataframe(pitcher_df[[c for c in cols if c in df.columns]], use_container_width=True)
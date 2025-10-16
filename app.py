import streamlit as st
import pandas as pd
import plotly.express as px

# ตั้งค่าให้หน้าเว็บแสดงผลแบบเต็มความกว้าง
st.set_page_config(layout="wide")

# --- Function สำหรับแปลง DataFrame เป็น CSV ---
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- ฟังก์ชันคำนวณ Combination (เหมือนเดิม) ---
def calculate_combinations(df_forces_filtered):
    value_cols = ['P', 'V2', 'V3', 'T', 'M2', 'M3']
    group_cols = ['Story', 'Column', 'Unique Name', 'Station']
    pivot_df = df_forces_filtered.pivot_table(index=group_cols, columns='Output Case', values=value_cols, fill_value=0)
    pivot_df.columns = ['_'.join(map(str, col)).strip() for col in pivot_df.columns.values]
    pivot_df.reset_index(inplace=True)
    required_cases = ['Dead', 'Live', 'SDL', 'EX', 'EY']
    for case in required_cases:
        for val in value_cols:
            col_name = f'{val}_{case}'
            if col_name not in pivot_df.columns:
                pivot_df[col_name] = 0
    combinations = {
        'U01': {'Dead': 1.4, 'SDL': 1.4, 'Live': 1.7}, 'U02': {'Dead': 1.05, 'SDL': 1.05, 'Live': 1.275, 'EX': 1},
        'U03': {'Dead': 1.05, 'SDL': 1.05, 'Live': 1.275, 'EX': -1}, 'U04': {'Dead': 1.05, 'SDL': 1.05, 'Live': 1.275, 'EY': 1},
        'U05': {'Dead': 1.05, 'SDL': 1.05, 'Live': 1.275, 'EY': -1}, 'U06': {'Dead': 0.9, 'SDL': 0.9, 'EX': 1},
        'U07': {'Dead': 0.9, 'SDL': 0.9, 'EX': -1}, 'U08': {'Dead': 0.9, 'SDL': 0.9, 'EY': 1},
        'U09': {'Dead': 0.9, 'SDL': 0.9, 'EY': -1},
    }
    combo_dfs = []
    for name, factors in combinations.items():
        temp_df = pivot_df[group_cols].copy()
        formula_parts = [f"{v:+g}{k}" for k, v in factors.items()]
        formula_string = "".join(formula_parts).lstrip('+')
        temp_df['Output Case'] = f"{name}: {formula_string}"
        for val_col in value_cols:
            total_val = sum(pivot_df.get(f'{val_col}_{case}', 0) * factor * (2.5 if val_col in ['V2', 'V3'] and case in ['EX', 'EY'] else 1) for case, factor in factors.items())
            temp_df[val_col] = total_val
        combo_dfs.append(temp_df)
    return pd.concat(combo_dfs, ignore_index=True)

# --- ส่วนของการประมวลผลไฟล์หลัก (Function) ---
@st.cache_data
def process_excel_data(uploaded_excel_file):
    """
    ฟังก์ชันหลักในการประมวลผลข้อมูลจากไฟล์ Excel
    จะ return ค่า 3 อย่างคือ:
    1. df_final: DataFrame ที่คำนวณและรวมพิกัดแล้ว (ไม่รวมชั้นใต้ดิน)
    2. df_forces_filtered: DataFrame ดิบก่อนคำนวณ เพื่อใช้เป็นข้อมูลตั้งต้น
    3. df_merged_coords: DataFrame ที่เก็บข้อมูลพิกัดเพื่อใช้ซ้ำ
    """
    try:
        df_forces = pd.read_excel(uploaded_excel_file, sheet_name='Element Forces - Columns', header=1).drop(0).reset_index(drop=True)
        df_connectivity = pd.read_excel(uploaded_excel_file, sheet_name='Column Object Connectivity', header=1).drop(0).reset_index(drop=True)
        df_points = pd.read_excel(uploaded_excel_file, sheet_name='Point Object Connectivity', header=1).drop(0).reset_index(drop=True)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการอ่านชีทจากไฟล์ Excel: {e}")
        return None, None, None

    # --- Data Cleaning and Type Conversion ---
    df_forces.columns = df_forces.columns.str.strip()
    df_connectivity.columns = df_connectivity.columns.str.strip()
    df_points.columns = df_points.columns.str.strip()
    for col in ['P', 'V2', 'V3', 'T', 'M2', 'M3', 'Station']: df_forces[col] = pd.to_numeric(df_forces[col], errors='coerce')
    for col in ['Length', 'Unique Name', 'UniquePtI', 'UniquePtJ']: df_connectivity[col] = pd.to_numeric(df_connectivity[col], errors='coerce')
    for col in ['UniqueName', 'X', 'Y', 'Z']: df_points[col] = pd.to_numeric(df_points[col], errors='coerce')
    df_forces.dropna(subset=['P', 'V2', 'V3', 'T', 'M2', 'M3', 'Station'], inplace=True)
    
    # --- Filter for allowed cases ---
    df_forces['Output Case'] = df_forces['Output Case'].str.strip()
    allowed_cases = ['Dead', 'Live', 'SDL', 'EX', 'EY']
    df_forces_filtered = df_forces[df_forces['Output Case'].isin(allowed_cases)]
    
    # --- คำนวณ Combination สำหรับข้อมูลปกติ ---
    df_combinations = calculate_combinations(df_forces_filtered)

    # --- <<<<<<<<<<<<<<< จุดแก้ไขที่ 1: เตรียม df_merged_coords ไว้ใช้กลาง >>>>>>>>>>>>>>> ---
    df_conn_subset = df_connectivity[['Unique Name', 'UniquePtI', 'UniquePtJ', 'Length']]
    df_points_coords = df_points[['UniqueName', 'X', 'Y', 'Z']].drop_duplicates(subset=['UniqueName'])
    df_merged_coords = pd.merge(df_conn_subset, df_points_coords, left_on='UniquePtI', right_on='UniqueName', how='left').rename(columns={'Z': 'UniquePtI_Z'}).drop(columns=['UniqueName', 'X', 'Y'])
    df_merged_coords = pd.merge(df_merged_coords, df_points_coords, left_on='UniquePtJ', right_on='UniqueName', how='left').rename(columns={'X': 'X', 'Y': 'Y', 'Z': 'UniquePtJ_Z'}).drop(columns=['UniqueName'])
    
    # --- รวมข้อมูลปกติกับพิกัด ---
    df_final = pd.merge(df_combinations, df_merged_coords, on='Unique Name', how='left')
    df_final.dropna(subset=['Station', 'Length', 'UniquePtI_Z', 'UniquePtJ_Z'], inplace=True)
    df_final = df_final[df_final['Length'] > 0].copy()
    df_final['Z_true'] = df_final['UniquePtI_Z'] + (df_final['Station'] / df_final['Length']) * (df_final['UniquePtJ_Z'] - df_final['UniquePtI_Z'])
    
    final_cols = ['Story', 'Column', 'Unique Name', 'Output Case', 'Station', 'P', 'V2', 'V3', 'T', 'M2', 'M3', 'X', 'Y', 'Z_true']
    return df_final[final_cols], df_forces_filtered, df_merged_coords

# --- ส่วนของหน้าเว็บ (Streamlit UI) ---
st.title("🏗️ Column Force Map Generator")

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Controls")
    excel_file = st.file_uploader("1. อัปโหลดไฟล์ Excel (.xlsx)", type="xlsx")

    if excel_file:
        if 'initial_data_processed' not in st.session_state or st.session_state.excel_file_name != excel_file.name:
            # --- <<<<<<<<<<<<<<< จุดแก้ไขที่ 2: รับ df_coords_map มาเก็บใน session_state >>>>>>>>>>>>>>> ---
            st.session_state.df_base_result, st.session_state.df_raw_forces, st.session_state.df_coords_map = process_excel_data(excel_file)
            st.session_state.excel_file_name = excel_file.name
            st.session_state.initial_data_processed = True
            st.session_state.processed_df = st.session_state.df_base_result.copy() if st.session_state.df_base_result is not None else None

        if st.session_state.processed_df is not None:
            st.success("ประมวลผลสำเร็จ!")
            st.divider()

            with st.expander("คำนวณเพิ่มเติมสำหรับชั้นใต้ดิน (Underground)"):
                calc_ug = st.checkbox("เปิดใช้งานการคำนวณชั้นใต้ดิน")
                if calc_ug:
                    stories = sorted(st.session_state.df_raw_forces['Story'].unique())
                    base_story = st.selectbox("เลือกชั้นที่จะใช้เป็นฐานในการคำนวณ:", options=stories)
                    st.write("กรอกตัวคูณ (Factor) ที่ต้องการ:")
                    col1, col2, col3 = st.columns(3)
                    factor_dead = col1.number_input("Factor for Dead", value=1.0)
                    factor_sdl = col2.number_input("Factor for SDL", value=1.0)
                    factor_live = col3.number_input("Factor for Live", value=1.0)

                    if st.button("คำนวณและเพิ่มชั้นใต้ดิน", type="primary"):
                        with st.spinner('กำลังสร้างข้อมูลชั้นใต้ดิน... ⏳'):
                            base_floor_df = st.session_state.df_raw_forces[st.session_state.df_raw_forces['Story'] == base_story].copy()
                            value_cols_ug = ['P', 'V2', 'V3', 'T', 'M2', 'M3']
                            factors_map = {'Dead': factor_dead, 'SDL': factor_sdl, 'Live': factor_live}
                            dfs_to_combine = []
                            unmodified_mask = ~base_floor_df['Output Case'].isin(factors_map.keys())
                            dfs_to_combine.append(base_floor_df[unmodified_mask])
                            for case, factor in factors_map.items():
                                if factor != 1.0:
                                    mask = base_floor_df['Output Case'] == case
                                    if mask.any():
                                        modified_part = base_floor_df[mask].copy()
                                        modified_part[value_cols_ug] *= factor
                                        dfs_to_combine.append(modified_part)
                                else: # Factor is 1.0
                                    dfs_to_combine.append(base_floor_df[base_floor_df['Output Case'] == case])
                            
                            ug_df_raw = pd.concat(dfs_to_combine, ignore_index=True)
                            ug_df_raw['Story'] = "Underground"
                            ug_combinations_df = calculate_combinations(ug_df_raw)
                            
                            # --- <<<<<<<<<<<<<<< จุดแก้ไขที่ 3: Merge ชั้นใต้ดินกับพิกัด! >>>>>>>>>>>>>>> ---
                            # นำผลคำนวณชั้นใต้ดินมา Merge กับตารางพิกัดที่เตรียมไว้
                            ug_final_df = pd.merge(ug_combinations_df, st.session_state.df_coords_map, on='Unique Name', how='left')
                            # คำนวณ Z_true สำหรับชั้นใต้ดิน
                            ug_final_df.dropna(subset=['Station', 'Length', 'UniquePtI_Z', 'UniquePtJ_Z'], inplace=True)
                            ug_final_df = ug_final_df[ug_final_df['Length'] > 0].copy()
                            ug_final_df['Z_true'] = ug_final_df['UniquePtI_Z'] + (ug_final_df['Station'] / ug_final_df['Length']) * (ug_final_df['UniquePtJ_Z'] - ug_final_df['UniquePtI_Z'])
                            
                            # รวมกับผลลัพธ์หลัก
                            st.session_state.processed_df = pd.concat([st.session_state.df_base_result, ug_final_df], ignore_index=True)
                            st.success("✔️ เพิ่มข้อมูลชั้นใต้ดินพร้อมพิกัดแล้ว!")
                            st.rerun()

                if st.button("รีเซ็ต (แสดงข้อมูลปกติ)"):
                    st.session_state.processed_df = st.session_state.df_base_result.copy()
                    st.info("รีเซ็ตเป็นข้อมูลปกติแล้ว")
                    st.rerun()
            st.divider()

            # --- ส่วนที่เหลือของ Sidebar (เหมือนเดิม) ---
            processed_df = st.session_state.processed_df
            with st.expander("ดูและดาวน์โหลดผลลัพธ์ทั้งหมด"):
                st.dataframe(processed_df)
                st.download_button(label="📥 ดาวน์โหลดผลลัพธ์ทั้งหมด", data=convert_df_to_csv(processed_df), file_name='column_processed_results.csv', mime='text/csv')
            st.divider()
            story_list = sorted(processed_df['Story'].unique(), key=lambda x: (x != 'Underground', str(x)), reverse=True)
            if 'story' not in st.session_state or st.session_state.story not in story_list: st.session_state.story = story_list[0]
            st.subheader("เลือกชั้น")
            st.selectbox("เลือกโดยตรง:", options=story_list, key='story')
            # ... (โค้ดส่วนควบคุมที่เหลือเหมือนเดิม) ...

# --- Main Panel Display (เหมือนเดิมทั้งหมด) ---
if not excel_file:
    st.info("กรุณาอัปโหลดไฟล์ Excel ในแถบด้านข้าง (Sidebar) เพื่อเริ่มต้น")
elif 'processed_df' in st.session_state and st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df
    selected_story = st.session_state.story
    # ... (โค้ดส่วนแสดงผลกราฟเหมือนเดิมทั้งหมด) ...
    st.header(f"🗺️ แผนที่แสดงค่าสูงสุดสำหรับชั้น: {selected_story}")
    # ... (ที่เหลือเหมือนเดิม) ...

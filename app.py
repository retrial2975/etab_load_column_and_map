import streamlit as st
import pandas as pd
import plotly.express as px

# ตั้งค่าให้หน้าเว็บแสดงผลแบบเต็มความกว้าง
st.set_page_config(layout="wide")

# --- Function สำหรับแปลง DataFrame เป็น CSV ---
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- ส่วนของการคำนวณ (Function) ---
@st.cache_data
def process_excel_data(uploaded_excel_file):
    """
    ฟังก์ชันหลักในการประมวลผลข้อมูลจากไฟล์ Excel ที่อัปโหลด
    """
    try:
        df_forces = pd.read_excel(uploaded_excel_file, sheet_name='Element Forces - Columns', header=1).drop(0).reset_index(drop=True)
        df_connectivity = pd.read_excel(uploaded_excel_file, sheet_name='Column Object Connectivity', header=1).drop(0).reset_index(drop=True)
        df_points = pd.read_excel(uploaded_excel_file, sheet_name='Point Object Connectivity', header=1).drop(0).reset_index(drop=True)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการอ่านชีทจากไฟล์ Excel: {e}")
        st.error("กรุณาตรวจสอบว่าไฟล์ Excel มีชีทชื่อ 'Element Forces - Columns', 'Column Object Connectivity', และ 'Point Object Connectivity' ครบถ้วน")
        return None

    # ล้างชื่อคอลัมน์
    df_forces.columns = df_forces.columns.str.strip()
    df_connectivity.columns = df_connectivity.columns.str.strip()
    df_points.columns = df_points.columns.str.strip()

    # --- แปลงชนิดข้อมูลล่วงหน้า ---
    force_numeric_cols = ['P', 'V2', 'V3', 'T', 'M2', 'M3', 'Station']
    for col in force_numeric_cols:
        df_forces[col] = pd.to_numeric(df_forces[col], errors='coerce')

    conn_numeric_cols = ['Length', 'Unique Name', 'UniquePtI', 'UniquePtJ']
    for col in conn_numeric_cols:
        df_connectivity[col] = pd.to_numeric(df_connectivity[col], errors='coerce')

    point_numeric_cols = ['UniqueName', 'X', 'Y', 'Z']
    for col in point_numeric_cols:
        df_points[col] = pd.to_numeric(df_points[col], errors='coerce')
    
    df_forces.dropna(subset=force_numeric_cols, inplace=True)
    
    # --- คำนวณ Combination ---
    df_forces['Output Case'] = df_forces['Output Case'].str.strip()
    allowed_cases = ['Dead', 'Live', 'SDL', 'EX', 'EY']
    df_forces_filtered = df_forces[df_forces['Output Case'].isin(allowed_cases)]
    
    value_cols = ['P', 'V2', 'V3', 'T', 'M2', 'M3']
    group_cols = ['Story', 'Column', 'Unique Name', 'Station']
    pivot_df = df_forces_filtered.pivot_table(index=group_cols, columns='Output Case', values=value_cols, fill_value=0)
    pivot_df.columns = ['_'.join(map(str, col)).strip() for col in pivot_df.columns.values]
    pivot_df.reset_index(inplace=True)

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
    df_combinations = pd.concat(combo_dfs, ignore_index=True)

    # --- <<<<<<<<<<<<<<< ส่วนที่แก้ไขข้อผิดพลาด >>>>>>>>>>>>>>> ---
    # เลือกเฉพาะคอลัมน์ที่จำเป็นจาก df_connectivity เพื่อป้องกันชื่อซ้ำซ้อน
    df_conn_subset = df_connectivity[['Unique Name', 'UniquePtI', 'UniquePtJ', 'Length']]
    
    df_points_coords = df_points[['UniqueName', 'X', 'Y', 'Z']].drop_duplicates()
    
    # ทำการ Merge โดยใช้ df_conn_subset ที่เลือกคอลัมน์แล้ว
    df_merged_coords = pd.merge(df_conn_subset, df_points_coords, left_on='UniquePtI', right_on='UniqueName', how='left').rename(columns={'Z': 'UniquePtI_Z'}).drop(columns=['UniqueName'])
    df_merged_coords = pd.merge(df_merged_coords, df_points_coords, left_on='UniquePtJ', right_on='UniqueName', how='left').rename(columns={'X': 'X', 'Y': 'Y', 'Z': 'UniquePtJ_Z'}).drop(columns=['UniqueName'])
    # --- <<<<<<<<<<<<<<< จบส่วนที่แก้ไข >>>>>>>>>>>>>>> ---
    
    df_final = pd.merge(df_combinations, df_merged_coords, on='Unique Name', how='left')
    df_final.dropna(subset=['Station', 'Length', 'UniquePtI_Z', 'UniquePtJ_Z'], inplace=True)
    df_final = df_final[df_final['Length'] > 0].copy()
    df_final['Z_true'] = df_final['UniquePtI_Z'] + (df_final['Station'] / df_final['Length']) * (df_final['UniquePtJ_Z'] - df_final['UniquePtI_Z'])
    
    final_cols = ['Story', 'Column', 'Unique Name', 'Output Case', 'Station', 'P', 'V2', 'V3', 'T', 'M2', 'M3', 'X', 'Y', 'Z_true']
    return df_final[final_cols]

# --- ส่วนของหน้าเว็บ (Streamlit UI) ---
st.title("🏗️ Column Force Map Generator")

with st.sidebar:
    st.header("1. อัปโหลดไฟล์ Excel")
    st.info("ไฟล์ Excel ต้องมีชีทชื่อ:\n- `Element Forces - Columns`\n- `Column Object Connectivity`\n- `Point Object Connectivity`")
    excel_file = st.file_uploader("อัปโหลดไฟล์ข้อมูลจาก ETABS (.xlsx)", type="xlsx")

if excel_file:
    processed_df = process_excel_data(excel_file)
    if processed_df is not None:
        st.success("✔️ ประมวลผลไฟล์ Excel สำเร็จ!")
        st.header("2. ผลลัพธ์การคำนวณทั้งหมด")
        st.dataframe(processed_df)
        st.download_button(label="📥 ดาวน์โหลดผลลัพธ์ทั้งหมดเป็น CSV", data=convert_df_to_csv(processed_df), file_name='column_processed_results.csv', mime='text/csv')
        st.divider()

        st.header("3. สร้างแผนที่แรงในเสา")
        
        story_list = sorted(processed_df['Story'].unique())
        if 'story_index' not in st.session_state:
            st.session_state.story_index = 0

        col1, col2, col3 = st.columns([1, 2, 1])
        if col1.button('⬅️ ชั้นก่อนหน้า'):
            st.session_state.story_index = max(0, st.session_state.story_index - 1)
        if col3.button('ชั้นถัดไป ➡️'):
            st.session_state.story_index = min(len(story_list) - 1, st.session_state.story_index + 1)
        
        selected_story = story_list[st.session_state.story_index]
        col2.metric("ชั้นที่เลือก (Selected Story)", selected_story)
        
        st.subheader("เลือกเกณฑ์สำหรับแสดงค่าสูงสุด")
        criteria_options = {'P (แรงอัด)': 'P_comp', 'P (แรงดึง)': 'P_tens', 'V2': 'V2', 'V3': 'V3', 'T': 'T', 'M2': 'M2', 'M3': 'M3'}
        selected_criteria_key = st.radio("เลือกแรงที่ต้องการดู:", options=criteria_options.keys(), horizontal=True)
        selected_criteria = criteria_options[selected_criteria_key]
        
        df_story = processed_df[processed_df['Story'] == selected_story].copy()
        
        if not df_story.empty:
            idx = None
            if selected_criteria == 'P_comp':
                idx = df_story.groupby('Unique Name')['P'].idxmin()
            elif selected_criteria == 'P_tens':
                idx = df_story.groupby('Unique Name')['P'].idxmax()
            else:
                df_story[f'{selected_criteria}_abs'] = df_story[selected_criteria].abs()
                idx = df_story.groupby('Unique Name')[f'{selected_criteria}_abs'].idxmax()
            
            df_max_val = df_story.loc[idx]

            df_max_val['Case_Name_Short'] = df_max_val['Output Case'].str.split(':').str[0]
            value_to_display = df_max_val[selected_criteria.replace('_comp','').replace('_tens','')]
            df_max_val['Label'] = df_max_val['Case_Name_Short'] + f": {selected_criteria_key.split(' ')[0]}=" + value_to_display.round(2).astype(str)
            
            hover_cols = {
                'P': ':.2f', 'V2': ':.2f', 'V3': ':.2f', 
                'T': ':.2f', 'M2': ':.2f', 'M3': ':.2f',
                'X': True, 'Y': True, 'Output Case': True, 'Label': False
            }

            fig = px.scatter(df_max_val, x='X', y='Y', text='Label', hover_name='Column', hover_data=hover_cols,
                             title=f"แผนที่แสดงค่า {selected_criteria_key} สูงสุดสำหรับชั้น: {selected_story}")

            fig.update_traces(textposition='top center', textfont_size=10)
            fig.update_layout(xaxis_title="X Coordinate (m)", yaxis_title="Y Coordinate (m)", yaxis_scaleanchor="x", yaxis_scaleratio=1, height=700, showlegend=False)
            
            st.plotly_chart(fig, use_container_width=True)
            with st.expander("แสดงข้อมูลที่ใช้พล็อต"):
                st.dataframe(df_max_val[['Story', 'Column', 'Unique Name', 'X', 'Y', 'P', 'V2', 'V3', 'T', 'M2', 'M3', 'Output Case']])
        else:
            st.warning("ไม่พบข้อมูลสำหรับชั้นที่เลือก")
else:
    st.info("กรุณาอัปโหลดไฟล์ Excel (.xlsx) ในแถบด้านข้าง (Sidebar) เพื่อเริ่มต้น")

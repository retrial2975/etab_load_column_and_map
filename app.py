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

    df_forces.columns = df_forces.columns.str.strip()
    df_connectivity.columns = df_connectivity.columns.str.strip()
    df_points.columns = df_points.columns.str.strip()

    # --- Data Type Conversion ---
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
    
    # --- Combination Calculation ---
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

    df_conn_subset = df_connectivity[['Unique Name', 'UniquePtI', 'UniquePtJ', 'Length']]
    df_points_coords = df_points[['UniqueName', 'X', 'Y', 'Z']].drop_duplicates()
    df_merged_coords = pd.merge(df_conn_subset, df_points_coords, left_on='UniquePtI', right_on='UniqueName', how='left').rename(columns={'Z': 'UniquePtI_Z'}).drop(columns=['UniqueName', 'X', 'Y'])
    df_merged_coords = pd.merge(df_merged_coords, df_points_coords, left_on='UniquePtJ', right_on='UniqueName', how='left').rename(columns={'X': 'X', 'Y': 'Y', 'Z': 'UniquePtJ_Z'}).drop(columns=['UniqueName'])
    
    df_final = pd.merge(df_combinations, df_merged_coords, on='Unique Name', how='left')
    df_final.dropna(subset=['Station', 'Length', 'UniquePtI_Z', 'UniquePtJ_Z'], inplace=True)
    df_final = df_final[df_final['Length'] > 0].copy()

    df_final['Z_true'] = df_final['UniquePtI_Z'] + (df_final['Station'] / df_final['Length']) * (df_final['UniquePtJ_Z'] - df_final['UniquePtI_Z'])
    
    final_cols = ['Story', 'Column', 'Unique Name', 'Output Case', 'Station', 'P', 'V2', 'V3', 'T', 'M2', 'M3', 'X', 'Y', 'Z_true']
    return df_final[final_cols]

# --- ส่วนของหน้าเว็บ (Streamlit UI) ---
st.title("🏗️ Column Force Map Generator")

# --- Sidebar Controls ---
with st.sidebar:
    st.header("⚙️ Controls")
    
    excel_file = st.file_uploader(
        "1. อัปโหลดไฟล์ Excel (.xlsx)", 
        type="xlsx",
        help="ไฟล์ Excel ต้องมีชีทชื่อ: 'Element Forces - Columns', 'Column Object Connectivity', 'Point Object Connectivity'"
    )

    if excel_file:
        processed_df = process_excel_data(excel_file)
        if processed_df is not None:
            st.success("ประมวลผลสำเร็จ!")
            st.divider()

            with st.expander("ดูและดาวน์โหลดผลลัพธ์ทั้งหมด"):
                st.dataframe(processed_df)
                st.download_button(label="📥 ดาวน์โหลดผลลัพธ์ทั้งหมด", data=convert_df_to_csv(processed_df), file_name='column_processed_results.csv', mime='text/csv')
            
            st.divider()
            
            st.subheader("2. เลือกชั้น")
            story_list = sorted(processed_df['Story'].unique(), reverse=True)
            criteria_options = {'P (แรงอัด)': 'P_comp', 'P (แรงดึง)': 'P_tens', 'V2': 'V2', 'V3': 'V3', 'T': 'T', 'M2': 'M2', 'M3': 'M3'}

            # --- <<<<<<<<<<<<<<< ส่วนที่ปรับปรุง >>>>>>>>>>>>>>> ---
            # 1. Initialize ค่าของทุกปุ่มไว้ใน session_state ถ้ายังไม่มี
            if 'story_index' not in st.session_state or st.session_state.story_index >= len(story_list):
                st.session_state.story_index = 0
            # **เพิ่มการจดจำค่าของ Radio button**
            if 'criteria_key' not in st.session_state:
                st.session_state.criteria_key = list(criteria_options.keys())[0]

            def update_story_index_from_selectbox():
                st.session_state.story_index = story_list.index(st.session_state.story_selectbox)

            col1, col2 = st.columns(2)
            if col1.button('⬅️ ชั้นบน'): st.session_state.story_index = max(0, st.session_state.story_index - 1); st.rerun()
            if col2.button('ชั้นล่าง ➡️'): st.session_state.story_index = min(len(story_list) - 1, st.session_state.story_index + 1); st.rerun()
                
            selected_story = st.selectbox(
                "หรือเลือกโดยตรง:", 
                options=story_list, 
                index=st.session_state.story_index, 
                key='story_selectbox', 
                on_change=update_story_index_from_selectbox
            )
            
            st.divider()
            
            st.subheader("3. เลือกเกณฑ์ค่าสูงสุด")
            # 2. ให้ Radio button บันทึกค่าลงใน session_state โดยตรงผ่าน key
            st.radio("เลือกแรงที่ต้องการดู:", options=criteria_options.keys(), key='criteria_key')
            # --- <<<<<<<<<<<<<<< จบส่วนที่ปรับปรุง >>>>>>>>>>>>>>> ---
            
# --- Main Panel Display ---
if not excel_file:
    st.info("กรุณาอัปโหลดไฟล์ Excel ในแถบด้านข้าง (Sidebar) เพื่อเริ่มต้น")
elif 'processed_df' in locals() and processed_df is not None:
    # 3. อ่านค่าที่ถูกต้องจาก session_state มาใช้งานเสมอ
    selected_criteria_key = st.session_state.criteria_key
    
    st.header(f"🗺️ แผนที่แสดงค่า {selected_criteria_key} สูงสุดสำหรับชั้น: {selected_story}")

    selected_criteria_col = selected_criteria_key.split(' ')[0]
    df_story = processed_df[processed_df['Story'] == selected_story].copy()
    
    if not df_story.empty:
        idx = None
        if selected_criteria_key == 'P (แรงอัด)': idx = df_story.groupby('Unique Name')['P'].idxmin()
        elif selected_criteria_key == 'P (แรงดึง)': idx = df_story.groupby('Unique Name')['P'].idxmax()
        else:
            df_story[f'{selected_criteria_col}_abs'] = df_story[selected_criteria_col].abs()
            idx = df_story.groupby('Unique Name')[f'{selected_criteria_col}_abs'].idxmax()
        
        df_max_val = df_story.loc[idx].reset_index(drop=True)

        if selected_criteria_key == 'P (แรงดึง)':
            df_max_val = df_max_val[df_max_val['P'] > 0].copy()

        if not df_max_val.empty:
            df_max_val['Case_Name_Short'] = df_max_val['Output Case'].str.split(':').str[0]
            value_to_display = df_max_val[selected_criteria_col]
            df_max_val['Label'] = df_max_val['Case_Name_Short'] + f": {selected_criteria_col}=" + value_to_display.round(2).astype(str)
            
            padding_x = (processed_df['X'].max() - processed_df['X'].min()) * 0.05
            padding_y = (processed_df['Y'].max() - processed_df['Y'].min()) * 0.05
            x_range = [processed_df['X'].min() - padding_x, processed_df['X'].max() + padding_x]
            y_range = [processed_df['Y'].min() - padding_y, processed_df['Y'].max() + padding_y]

            custom_data_cols = ['P', 'V2', 'V3', 'T', 'M2', 'M3', 'Output Case']
            fig = px.scatter(
                df_max_val, x='X', y='Y', 
                text='Label',
                color=value_to_display,
                color_continuous_scale='RdBu',
                hover_name='Column',
                custom_data=custom_data_cols
            )
            hovertemplate = (
                "<b>%{hovertext}</b><br><br>"
                "X: %{x:.2f}<br>Y: %{y:.2f}<br>"
                "<br><b>--- Forces ---</b><br>"
                "P: %{customdata[0]:.2f}<br>V2: %{customdata[1]:.2f}<br>"
                "V3: %{customdata[2]:.2f}<br>T: %{customdata[3]:.2f}<br>"
                "M2: %{customdata[4]:.2f}<br>M3: %{customdata[5]:.2f}<br>"
                "<b>Output Case:</b> %{customdata[6]}"
                "<extra></extra>"
            )
            fig.update_traces(textposition='top center', textfont_size=10, hovertemplate=hovertemplate)
            fig.update_layout(
                xaxis_range=x_range, yaxis_range=y_range,
                xaxis_title="X Coordinate (m)", yaxis_title="Y Coordinate (m)",
                yaxis_scaleanchor="x", yaxis_scaleratio=1, height=700,
                coloraxis_colorbar_title_text=selected_criteria_key
            )
            st.plotly_chart(fig, use_container_width=True)
            
            with st.expander("แสดงข้อมูลที่ใช้พล็อต และดาวน์โหลด"):
                st.dataframe(df_max_val[['Story', 'Column', 'Unique Name', 'X', 'Y', 'P', 'V2', 'V3', 'T', 'M2', 'M3', 'Output Case']])
                st.download_button(label="📥 ดาวน์โหลดข้อมูลที่พล็อตเป็น CSV", data=convert_df_to_csv(df_max_val), file_name=f'plot_data_{selected_story}_{selected_criteria_col}.csv', mime='text/csv')
        else:
            st.info(f"ไม่พบเสาที่ตรงตามเงื่อนไข '{selected_criteria_key}' ในชั้น {selected_story}")
    elif excel_file is not None:
        st.warning("ไม่สามารถประมวลผลไฟล์ได้ กรุณาตรวจสอบข้อความ Error ที่แสดงผล")

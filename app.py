import streamlit as st
import pandas as pd
import plotly.express as px

# ตั้งค่าให้หน้าเว็บแสดงผลแบบเต็มความกว้าง
st.set_page_config(layout="wide")

# --- Function สำหรับแปลง DataFrame เป็น CSV ---
@st.cache_data
def convert_df_to_csv(df):
    # ฟังก์ชันสำคัญ: แปลง DataFrame เป็นไฟล์ CSV (bytes) สำหรับปุ่ม Download
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

    # (ส่วนการคำนวณทั้งหมดเหมือนเดิมทุกประการ)
    df_forces.columns = df_forces.columns.str.strip()
    df_connectivity.columns = df_connectivity.columns.str.strip()
    df_points.columns = df_points.columns.str.strip()

    df_forces['Station'] = pd.to_numeric(df_forces['Station'], errors='coerce')
    force_numeric_cols = ['P', 'V2', 'V3', 'T', 'M2', 'M3']
    for col in force_numeric_cols:
        df_forces[col] = pd.to_numeric(df_forces[col], errors='coerce')
    df_forces.dropna(subset=['Station'] + force_numeric_cols, inplace=True)

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
        temp_df['Output Case'] = name
        for val_col in value_cols:
            total_val = 0
            for case, factor in factors.items():
                current_factor = factor
                if val_col in ['V2', 'V3'] and case in ['EX', 'EY']:
                    current_factor *= 2.5
                col_name = f'{val_col}_{case}'
                if col_name in pivot_df.columns:
                    total_val += pivot_df[col_name] * current_factor
            temp_df[val_col] = total_val
        combo_dfs.append(temp_df)
    df_combinations = pd.concat(combo_dfs, ignore_index=True)

    df_connectivity['Length'] = pd.to_numeric(df_connectivity['Length'], errors='coerce')
    df_connectivity['Unique Name'] = pd.to_numeric(df_connectivity['Unique Name'], errors='coerce')
    df_connectivity['UniquePtI'] = pd.to_numeric(df_connectivity['UniquePtI'], errors='coerce')
    df_connectivity['UniquePtJ'] = pd.to_numeric(df_connectivity['UniquePtJ'], errors='coerce')
    point_numeric_cols = ['UniqueName', 'X', 'Y', 'Z']
    for col in point_numeric_cols:
        df_points[col] = pd.to_numeric(df_points[col], errors='coerce')

    df_points_coords = df_points[['UniqueName', 'X', 'Y', 'Z']].drop_duplicates()
    df_merged_coords = pd.merge(
        df_connectivity[['Unique Name', 'UniquePtI', 'UniquePtJ', 'Length']],
        df_points_coords, left_on='UniquePtI', right_on='UniqueName', how='left'
    ).rename(columns={'Z': 'UniquePtI_Z'}).drop(columns=['UniqueName', 'X', 'Y'])
    df_merged_coords = pd.merge(
        df_merged_coords,
        df_points_coords, left_on='UniquePtJ', right_on='UniqueName', how='left'
    ).rename(columns={'X': 'X', 'Y': 'Y', 'Z': 'UniquePtJ_Z'}).drop(columns=['UniqueName'])

    df_final = pd.merge(df_combinations, df_merged_coords, on='Unique Name', how='left')
    df_final.dropna(subset=['Station', 'Length', 'UniquePtI_Z', 'UniquePtJ_Z'], inplace=True)
    df_final = df_final[df_final['Length'] > 0].copy()

    df_final['Z_true'] = df_final['UniquePtI_Z'] + \
                        (df_final['Station'] / df_final['Length']) * (df_final['UniquePtJ_Z'] - df_final['UniquePtI_Z'])

    final_cols = ['Story', 'Column', 'Unique Name', 'Output Case', 'Station',
                  'P', 'V2', 'V3', 'T', 'M2', 'M3', 'X', 'Y', 'Z_true']
    return df_final[final_cols]


# --- ส่วนของหน้าเว็บ (Streamlit UI) ---

st.title("🏗️ Column Force Map Generator (Excel Version)")

# --- Uploader Section ---
with st.sidebar:
    st.header("1. อัปโหลดไฟล์ Excel")
    st.info("ไฟล์ Excel ต้องมีชีทชื่อ:\n- `Element Forces - Columns`\n- `Column Object Connectivity`\n- `Point Object Connectivity`")
    excel_file = st.file_uploader("อัปโหลดไฟล์ข้อมูลจาก ETABS (.xlsx)", type="xlsx")

# --- Main Panel ---
if excel_file:
    processed_df = process_excel_data(excel_file)
    
    if processed_df is not None:
        st.success("✔️ ประมวลผลไฟล์ Excel สำเร็จ!")
        
        # --- <<<<<<<<<<<<<<< ส่วนที่เพิ่มเข้ามา >>>>>>>>>>>>>>> ---
        st.header("2. ผลลัพธ์การคำนวณทั้งหมด")
        st.write("คุณสามารถตรวจสอบข้อมูลทั้งหมดที่ผ่านการประมวลผลแล้วในตารางด้านล่าง และดาวน์โหลดเป็นไฟล์ CSV ได้")
        
        st.dataframe(processed_df)
        
        csv_data = convert_df_to_csv(processed_df)
        st.download_button(
           label="📥 ดาวน์โหลดผลลัพธ์ทั้งหมดเป็น CSV",
           data=csv_data,
           file_name='column_processed_results.csv',
           mime='text/csv',
        )
        st.divider()
        # --- <<<<<<<<<<<<<<< จบส่วนที่เพิ่มเข้ามา >>>>>>>>>>>>>>> ---
        
        # ส่วนของการพล็อตกราฟ (ปรับลำดับเป็นข้อ 3)
        st.header("3. สร้างแผนที่แรงในเสา")
        story_list = processed_df['Story'].unique()
        selected_story = st.selectbox("เลือกชั้น (Story) ที่ต้องการพล็อต:", options=story_list)

        df_story = processed_df[processed_df['Story'] == selected_story].copy()
        
        st.subheader(f"🗺️ แผนที่แรง P สูงสุดสำหรับชั้น: {selected_story}")

        if not df_story.empty:
            df_story['P_abs'] = df_story['P'].abs()
            df_max_p = df_story.loc[df_story.groupby('Unique Name')['P_abs'].idxmax()]
            df_max_p['Label'] = df_max_p['Output Case'] + ": " + df_max_p['P'].round(2).astype(str)

            fig = px.scatter(df_max_p, x='X', y='Y',
                             text='Label',
                             hover_name='Column',
                             hover_data={'X': True, 'Y': True, 'P': ':.2f', 'Output Case': True, 'Label': False},
                             title=f"Maximum Axial Force (P) on Story: {selected_story}")

            fig.update_traces(textposition='top center', textfont_size=10)
            fig.update_layout(
                xaxis_title="X Coordinate (m)",
                yaxis_title="Y Coordinate (m)",
                yaxis_scaleanchor="x",
                yaxis_scaleratio=1,
                height=700,
                showlegend=False
            )
            
            st.plotly_chart(fig, use_container_width=True)

            with st.expander("แสดงข้อมูลที่ใช้พล็อต"):
                st.dataframe(df_max_p[['Story', 'Column', 'Unique Name', 'X', 'Y', 'P', 'Output Case']])
        else:
            st.warning("ไม่พบข้อมูลสำหรับชั้นที่เลือก")
else:
    st.info("กรุณาอัปโหลดไฟล์ Excel (.xlsx) ในแถบด้านข้าง (Sidebar) เพื่อเริ่มต้น")

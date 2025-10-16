import streamlit as st
import pandas as pd
import plotly.express as px

# ตั้งค่าให้หน้าเว็บแสดงผลแบบเต็มความกว้าง
st.set_page_config(layout="wide")

# --- Function สำหรับแปลง DataFrame เป็น CSV ---
@st.cache_data
def convert_df_to_csv(df):
    return df.to_csv(index=False).encode('utf-8')

# --- <<<<<<<<<<<<<<< ส่วนที่ 1: ยกฟังก์ชันคำนวณ Combination ออกมา >>>>>>>>>>>>>>> ---
# ยกส่วนการคำนวณ Combination ออกมาเป็นฟังก์ชันของตัวเองเพื่อให้เรียกใช้ซ้ำได้
# สำหรับการคำนวณปกติ และการคำนวณชั้นใต้ดิน
def calculate_combinations(df_forces_filtered):
    """
    คำนวณ Load Combinations จาก DataFrame ของแรงที่กรองแล้ว
    """
    value_cols = ['P', 'V2', 'V3', 'T', 'M2', 'M3']
    group_cols = ['Story', 'Column', 'Unique Name', 'Station']
    
    pivot_df = df_forces_filtered.pivot_table(index=group_cols, columns='Output Case', values=value_cols, fill_value=0)
    pivot_df.columns = ['_'.join(map(str, col)).strip() for col in pivot_df.columns.values]
    pivot_df.reset_index(inplace=True)

    # ตรวจสอบว่ามี Case ที่จำเป็นครบหรือไม่ ถ้าไม่มีให้สร้างคอลัมน์เปล่าขึ้นมา
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
    ฟังก์ชันหลักในการประมวลผลข้อมูลจากไฟล์ Excel ที่อัปโหลด
    จะ return ค่า 2 อย่างคือ:
    1. df_final: DataFrame ที่ผ่านการคำนวณ Combination แล้ว (ไม่รวมชั้นใต้ดิน)
    2. df_forces_filtered: DataFrame ดิบก่อนการคำนวณ เพื่อใช้เป็นข้อมูลตั้งต้นสำหรับชั้นใต้ดิน
    """
    try:
        df_forces = pd.read_excel(uploaded_excel_file, sheet_name='Element Forces - Columns', header=1).drop(0).reset_index(drop=True)
        df_connectivity = pd.read_excel(uploaded_excel_file, sheet_name='Column Object Connectivity', header=1).drop(0).reset_index(drop=True)
        df_points = pd.read_excel(uploaded_excel_file, sheet_name='Point Object Connectivity', header=1).drop(0).reset_index(drop=True)
    except Exception as e:
        st.error(f"เกิดข้อผิดพลาดในการอ่านชีทจากไฟล์ Excel: {e}")
        st.error("กรุณาตรวจสอบว่าไฟล์ Excel มีชีทชื่อ 'Element Forces - Columns', 'Column Object Connectivity', และ 'Point Object Connectivity' ครบถ้วน")
        return None, None

    # --- Data Cleaning and Type Conversion ---
    df_forces.columns = df_forces.columns.str.strip()
    df_connectivity.columns = df_connectivity.columns.str.strip()
    df_points.columns = df_points.columns.str.strip()
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
    
    # --- Filter for allowed cases ---
    df_forces['Output Case'] = df_forces['Output Case'].str.strip()
    allowed_cases = ['Dead', 'Live', 'SDL', 'EX', 'EY']
    df_forces_filtered = df_forces[df_forces['Output Case'].isin(allowed_cases)]
    
    # --- คำนวณ Combination สำหรับข้อมูลปกติ ---
    df_combinations = calculate_combinations(df_forces_filtered)

    # --- Merge with coordinates data ---
    df_conn_subset = df_connectivity[['Unique Name', 'UniquePtI', 'UniquePtJ', 'Length']]
    df_points_coords = df_points[['UniqueName', 'X', 'Y', 'Z']].drop_duplicates()
    df_merged_coords = pd.merge(df_conn_subset, df_points_coords, left_on='UniquePtI', right_on='UniqueName', how='left').rename(columns={'Z': 'UniquePtI_Z'}).drop(columns=['UniqueName', 'X', 'Y'])
    df_merged_coords = pd.merge(df_merged_coords, df_points_coords, left_on='UniquePtJ', right_on='UniqueName', how='left').rename(columns={'X': 'X', 'Y': 'Y', 'Z': 'UniquePtJ_Z'}).drop(columns=['UniqueName'])
    
    df_final = pd.merge(df_combinations, df_merged_coords, on='Unique Name', how='left')
    df_final.dropna(subset=['Station', 'Length', 'UniquePtI_Z', 'UniquePtJ_Z'], inplace=True)
    df_final = df_final[df_final['Length'] > 0].copy()
    df_final['Z_true'] = df_final['UniquePtI_Z'] + (df_final['Station'] / df_final['Length']) * (df_final['UniquePtJ_Z'] - df_final['UniquePtI_Z'])
    
    final_cols = ['Story', 'Column', 'Unique Name', 'Output Case', 'Station', 'P', 'V2', 'V3', 'T', 'M2', 'M3', 'X', 'Y', 'Z_true']
    return df_final[final_cols], df_forces_filtered

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
        # ใช้ session_state เพื่อเก็บผลลัพธ์การประมวลผล ป้องกันการคำนวณซ้ำซ้อน
        if 'initial_data_processed' not in st.session_state or st.session_state.excel_file_name != excel_file.name:
            st.session_state.df_base_result, st.session_state.df_raw_forces = process_excel_data(excel_file)
            st.session_state.excel_file_name = excel_file.name
            st.session_state.initial_data_processed = True
            # ตั้งค่า processed_df เริ่มต้นให้เป็น df_base_result
            st.session_state.processed_df = st.session_state.df_base_result.copy()

        if st.session_state.processed_df is not None:
            st.success("ประมวลผลสำเร็จ!")
            st.divider()

            # --- <<<<<<<<<<<<<<< ส่วนที่ 2: เพิ่ม UI สำหรับคำนวณชั้นใต้ดิน >>>>>>>>>>>>>>> ---
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
                            # 1. ดึงข้อมูลดิบจากชั้นที่เลือกเป็นฐาน
                            base_floor_df = st.session_state.df_raw_forces[st.session_state.df_raw_forces['Story'] == base_story].copy()
                            
                            # 2. เตรียมข้อมูลดิบสำหรับชั้นใต้ดินโดยการคูณ Factor
                            value_cols_ug = ['P', 'V2', 'V3', 'T', 'M2', 'M3']
                            factors_map = {'Dead': factor_dead, 'SDL': factor_sdl, 'Live': factor_live}
                            
                            dfs_to_combine = []
                            # เก็บ Case ที่ไม่ต้องคูณค่า (เช่น EX, EY) ไว้เหมือนเดิม
                            unmodified_mask = ~base_floor_df['Output Case'].isin(factors_map.keys())
                            dfs_to_combine.append(base_floor_df[unmodified_mask])
                            
                            # คูณ Factor ให้กับ Case ที่กำหนด
                            for case, factor in factors_map.items():
                                mask = base_floor_df['Output Case'] == case
                                if mask.any():
                                    modified_part = base_floor_df[mask].copy()
                                    modified_part[value_cols_ug] *= factor
                                    dfs_to_combine.append(modified_part)
                            
                            ug_df_raw = pd.concat(dfs_to_combine).reset_index(drop=True)
                            ug_df_raw['Story'] = "Underground" # เปลี่ยนชื่อ Story
                            
                            # 3. คำนวณ Combination สำหรับชั้นใต้ดิน
                            ug_combinations_df = calculate_combinations(ug_df_raw)
                            
                            # 4. รวมผลลัพธ์ชั้นใต้ดินเข้ากับผลลัพธ์หลัก (ที่เก็บอยู่ใน df_base_result)
                            # ที่ต้องรวมกับ base result เพื่อป้องกันการกดปุ่มคำนวณซ้ำๆ แล้วข้อมูลใต้ดินจะถูกเพิ่มเข้าไปเรื่อยๆ
                            st.session_state.processed_df = pd.concat([st.session_state.df_base_result, ug_combinations_df], ignore_index=True)
                            st.success("✔️ เพิ่มข้อมูลชั้นใต้ดินแล้ว!")
                            st.rerun() # สั่งให้ UI รีเฟรชตัวเองเพื่อดึงข้อมูลใหม่
                
                # ปุ่มสำหรับรีเซ็ตกลับไปเป็นข้อมูลดั้งเดิม (ไม่มีชั้นใต้ดิน)
                if st.button("รีเซ็ต (แสดงข้อมูลปกติ)"):
                    st.session_state.processed_df = st.session_state.df_base_result.copy()
                    st.info("รีเซ็ตเป็นข้อมูลปกติแล้ว")
                    st.rerun()

            st.divider()

            processed_df = st.session_state.processed_df # ดึงข้อมูลล่าสุดจาก session_state มาใช้งาน
            
            with st.expander("ดูและดาวน์โหลดผลลัพธ์ทั้งหมด"):
                st.dataframe(processed_df)
                st.download_button(label="📥 ดาวน์โหลดผลลัพธ์ทั้งหมด", data=convert_df_to_csv(processed_df), file_name='column_processed_results.csv', mime='text/csv')
            
            st.divider()
            
            # --- ส่วนควบคุมการแสดงผล (เหมือนเดิม) ---
            story_list = sorted(processed_df['Story'].unique(), key=lambda x: (x != 'Underground', x), reverse=True)
            criteria_options = {'P (แรงอัด)': 'P_comp', 'P (แรงดึง)': 'P_tens', 'V2': 'V2', 'V3': 'V3', 'T': 'T', 'M2': 'M2', 'M3': 'M3'}
            combo_names = [f'U{i:02d}' for i in range(1, 10)]

            # Initialize session_state (เหมือนเดิม)
            if 'story' not in st.session_state or st.session_state.story not in story_list:
                st.session_state.story = story_list[0]
            if 'criteria' not in st.session_state:
                st.session_state.criteria = list(criteria_options.keys())[0]
            if 'show_combo_name' not in st.session_state: st.session_state.show_combo_name = True
            if 'show_force_value' not in st.session_state: st.session_state.show_force_value = True
            if 'selected_combos' not in st.session_state: st.session_state.selected_combos = combo_names

            st.subheader("ตั้งค่าการแสดงผล")
            st.toggle("แสดงชื่อ Combination (UXX)", key='show_combo_name')
            st.toggle("แสดงค่าแรง (Force Value)", key='show_force_value')
            st.divider()

            st.subheader("เลือกชั้น")
            def go_to_prev_story():
                current_index = story_list.index(st.session_state.story)
                st.session_state.story = story_list[min(len(story_list) - 1, current_index + 1)] if story_list[0] != 'Underground' else story_list[max(0, current_index - 1)]
            def go_to_next_story():
                current_index = story_list.index(st.session_state.story)
                st.session_state.story = story_list[max(0, current_index - 1)] if story_list[0] != 'Underground' else story_list[min(len(story_list) - 1, current_index + 1)]

            col1, col2 = st.columns(2)
            # แก้ไขเล็กน้อยเพื่อให้ปุ่มทำงานถูกต้องกับลำดับชั้นที่กลับด้าน
            col1.button('⬅️ ชั้นบน', on_click=go_to_next_story)
            col2.button('ชั้นล่าง ➡️', on_click=go_to_prev_story)
            st.selectbox("หรือเลือกโดยตรง:", options=story_list, key='story')
            
            st.divider()
            st.subheader("เลือกเกณฑ์ค่าสูงสุด")
            st.radio("เลือกแรงที่ต้องการดู:", options=criteria_options.keys(), key='criteria')
            st.divider()
            st.subheader("กรอง Load Combinations")
            def select_all(): st.session_state.selected_combos = combo_names
            def deselect_all(): st.session_state.selected_combos = []
            c1, c2 = st.columns(2)
            c1.button("เลือกทั้งหมด", on_click=select_all, use_container_width=True)
            c2.button("ยกเลิกทั้งหมด", on_click=deselect_all, use_container_width=True)
            st.multiselect("เลือก Combination ที่จะนำมาพิจารณา:", options=combo_names, key='selected_combos')

# --- Main Panel Display ---
if not excel_file:
    st.info("กรุณาอัปโหลดไฟล์ Excel ในแถบด้านข้าง (Sidebar) เพื่อเริ่มต้น")
# --- <<<<<<<<<<<<<<< ส่วนที่ 3: ปรับการแสดงผลหลักเล็กน้อย >>>>>>>>>>>>>>> ---
elif 'processed_df' in st.session_state and st.session_state.processed_df is not None:
    processed_df = st.session_state.processed_df # ดึงข้อมูลล่าสุดจาก session_state มาใช้งาน
    
    # อ่านค่าที่เลือกจาก session_state (เหมือนเดิม)
    selected_story = st.session_state.story
    selected_criteria_key = st.session_state.criteria
    selected_combos = st.session_state.selected_combos
    
    st.header(f"🗺️ แผนที่แสดงค่า {selected_criteria_key} สูงสุดสำหรับชั้น: {selected_story}")

    # --- ส่วนตรรกะการพล็ตกราฟ (เหมือนเดิมทั้งหมด) ---
    selected_criteria_col = selected_criteria_key.split(' ')[0]
    df_story = processed_df[processed_df['Story'] == selected_story].copy()
    
    df_story['ComboName'] = df_story['Output Case'].str.split(':').str[0]
    df_story_filtered = df_story[df_story['ComboName'].isin(selected_combos)]

    if not df_story_filtered.empty:
        idx = None
        if selected_criteria_key == 'P (แรงอัด)': idx = df_story_filtered.groupby('Unique Name')['P'].idxmin()
        elif selected_criteria_key == 'P (แรงดึง)': idx = df_story_filtered.groupby('Unique Name')['P'].idxmax()
        else:
            df_story_filtered = df_story_filtered.copy()
            df_story_filtered.loc[:, f'{selected_criteria_col}_abs'] = df_story_filtered[selected_criteria_col].abs()
            idx = df_story_filtered.groupby('Unique Name')[f'{selected_criteria_col}_abs'].idxmax()
        
        df_max_val = df_story_filtered.loc[idx].reset_index(drop=True)

        if selected_criteria_key == 'P (แรงดึง)':
            df_max_val = df_max_val[df_max_val['P'] > 0].copy()

        if not df_max_val.empty:
            def build_label(row):
                parts = []
                if st.session_state.show_combo_name: parts.append(row['Case_Name_Short'])
                if st.session_state.show_force_value: parts.append(f"{selected_criteria_col}={row[selected_criteria_col]:.2f}")
                return ": ".join(parts)
            
            df_max_val['Case_Name_Short'] = df_max_val['Output Case'].str.split(':').str[0]
            df_max_val['DisplayLabel'] = df_max_val.apply(build_label, axis=1)

            value_to_display = df_max_val[selected_criteria_col]
            # ใช้ข้อมูลทั้งหมดในการกำหนดขอบเขตของกราฟเพื่อให้แกนคงที่
            x_min, x_max = processed_df['X'].min(), processed_df['X'].max()
            y_min, y_max = processed_df['Y'].min(), processed_df['Y'].max()
            padding_x = (x_max - x_min) * 0.05
            padding_y = (y_max - y_min) * 0.05
            x_range = [x_min - padding_x, x_max + padding_x]
            y_range = [y_min - padding_y, y_max + padding_y]

            custom_data_cols = ['P', 'V2', 'V3', 'T', 'M2', 'M3', 'Output Case']
            fig = px.scatter(
                df_max_val, x='X', y='Y', text='DisplayLabel', color=value_to_display,
                color_continuous_scale='RdBu', hover_name='Column', custom_data=custom_data_cols
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
                display_cols = ['Story', 'Column', 'Unique Name', 'X', 'Y', 'P', 'V2', 'V3', 'T', 'M2', 'M3', 'Output Case']
                st.dataframe(df_max_val[display_cols])
                st.download_button(label="📥 ดาวน์โหลดข้อมูลที่พล็อตเป็น CSV", data=convert_df_to_csv(df_max_val), file_name=f'plot_data_{selected_story}_{selected_criteria_col}.csv', mime='text/csv')
        else:
            st.info(f"ไม่พบเสาที่ตรงตามเงื่อนไข '{selected_criteria_key}' ในชั้น {selected_story} (อาจจะเกิดจากการกรอง Combination ออกทั้งหมด)")
    else:
        st.warning("ไม่พบข้อมูลสำหรับชั้นที่เลือก หรือคุณอาจจะไม่ได้เลือก Combination ใดๆ เลย")
elif excel_file is not None:
    st.warning("ไม่สามารถประมวลผลไฟล์ได้ กรุณาตรวจสอบข้อความ Error ที่แสดงผล")

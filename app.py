import streamlit as st
import pandas as pd
import plotly.express as px

# Set page to wide layout
st.set_page_config(layout="wide")

# --- Helper Function to Convert DataFrame to CSV ---
@st.cache_data
def convert_df_to_csv(df):
    """Converts a DataFrame to a CSV file for the download button."""
    return df.to_csv(index=False).encode('utf-8')

# --- Main Data Processing Function ---
@st.cache_data
def process_excel_data(uploaded_excel_file):
    """
    Main function to process the uploaded Excel file.
    This version uses the stable logic from the first working version to prevent KeyErrors.
    """
    try:
        df_forces = pd.read_excel(uploaded_excel_file, sheet_name='Element Forces - Columns', header=1).drop(0).reset_index(drop=True)
        df_connectivity = pd.read_excel(uploaded_excel_file, sheet_name='Column Object Connectivity', header=1).drop(0).reset_index(drop=True)
        df_points = pd.read_excel(uploaded_excel_file, sheet_name='Point Object Connectivity', header=1).drop(0).reset_index(drop=True)
    except Exception as e:
        st.error(f"Error reading sheets from Excel file: {e}")
        st.error("Please ensure the Excel file contains the sheets: 'Element Forces - Columns', 'Column Object Connectivity', and 'Point Object Connectivity'.")
        return None

    # Clean column names
    df_forces.columns = df_forces.columns.str.strip()
    df_connectivity.columns = df_connectivity.columns.str.strip()
    df_points.columns = df_points.columns.str.strip()

    # --- Pre-computation Data Type Conversion ---
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

    # --- Coordinate Merging (The stable way to prevent KeyError) ---
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

# --- Streamlit UI ---
st.title("🏗️ Column Force Map Generator")

with st.sidebar:
    st.header("1. Upload Excel File")
    st.info("The Excel file must contain these sheets:\n- `Element Forces - Columns`\n- `Column Object Connectivity`\n- `Point Object Connectivity`")
    excel_file = st.file_uploader("Upload ETABS Data File (.xlsx)", type="xlsx")

if excel_file:
    processed_df = process_excel_data(excel_file)
    if processed_df is not None:
        st.success("✔️ Excel file processed successfully!")
        with st.expander("View and Download All Calculated Results"):
            st.dataframe(processed_df)
            st.download_button(label="📥 Download All Results as CSV", data=convert_df_to_csv(processed_df), file_name='column_processed_results.csv', mime='text/csv')
        st.divider()

        st.header("3. Create Column Force Map")
        
        # --- Story Selection (Hybrid: Buttons + Selectbox) ---
        story_list = sorted(processed_df['Story'].unique(), reverse=True)
        if 'story_index' not in st.session_state or st.session_state.story_index >= len(story_list):
            st.session_state.story_index = 0

        def update_story_index_from_selectbox():
            st.session_state.story_index = story_list.index(st.session_state.story_selectbox)

        col1, col2, col3 = st.columns([1, 4, 1])
        if col1.button('⬅️ Upper Story (Up)'):
            st.session_state.story_index = max(0, st.session_state.story_index - 1)
            st.rerun()
        if col3.button('Lower Story (Down) ➡️'):
            st.session_state.story_index = min(len(story_list) - 1, st.session_state.story_index + 1)
            st.rerun()
            
        selected_story = col2.selectbox("Or select story directly:", options=story_list, index=st.session_state.story_index, key='story_selectbox', on_change=update_story_index_from_selectbox)
        
        # --- Max Value Criteria Selection ---
        st.subheader("Select Criteria for Maximum Value Display")
        criteria_options = {'P (Compression)': 'P_comp', 'P (Tension)': 'P_tens', 'V2': 'V2', 'V3': 'V3', 'T': 'T', 'M2': 'M2', 'M3': 'M3'}
        selected_criteria_key = st.radio("Select force to view:", options=criteria_options.keys(), horizontal=True)
        selected_criteria_col = selected_criteria_key.split(' ')[0]
        
        df_story = processed_df[processed_df['Story'] == selected_story].copy()
        
        if not df_story.empty:
            idx = None
            if selected_criteria_key == 'P (Compression)': idx = df_story.groupby('Unique Name')['P'].idxmin()
            elif selected_criteria_key == 'P (Tension)': idx = df_story.groupby('Unique Name')['P'].idxmax()
            else:
                df_story[f'{selected_criteria_col}_abs'] = df_story[selected_criteria_col].abs()
                idx = df_story.groupby('Unique Name')[f'{selected_criteria_col}_abs'].idxmax()
            
            # --- The fix for the hover data issue ---
            df_max_val = df_story.loc[idx].reset_index(drop=True)

            df_max_val['Case_Name_Short'] = df_max_val['Output Case'].str.split(':').str[0]
            value_to_display = df_max_val[selected_criteria_col]
            df_max_val['Label'] = df_max_val['Case_Name_Short'] + f": {selected_criteria_col}=" + value_to_display.round(2).astype(str)
            
            # --- Fix Axes and Add Color Scale ---
            padding_x = (processed_df['X'].max() - processed_df['X'].min()) * 0.05
            padding_y = (processed_df['Y'].max() - processed_df['Y'].min()) * 0.05
            x_range = [processed_df['X'].min() - padding_x, processed_df['X'].max() + padding_x]
            y_range = [processed_df['Y'].min() - padding_y, processed_df['Y'].max() + padding_y]

            hover_data_config = {'P':'{:.2f}', 'V2':'{:.2f}', 'V3':'{:.2f}', 'T':'{:.2f}', 'M2':'{:.2f}', 'M3':'{:.2f}', 'Output Case':True, 'X':True, 'Y':True}

            fig = px.scatter(
                df_max_val, x='X', y='Y', text='Label',
                color=value_to_display,
                color_continuous_scale='RdBu', # Red (Negative/Compression), Blue (Positive/Tension)
                hover_name='Column',
                hover_data=hover_data_config,
                title=f"Map of Max {selected_criteria_key} for Story: {selected_story}"
            )

            fig.update_traces(textposition='top center', textfont_size=10)
            fig.update_layout(
                xaxis_range=x_range, yaxis_range=y_range,
                xaxis_title="X Coordinate (m)", yaxis_title="Y Coordinate (m)",
                yaxis_scaleanchor="x", yaxis_scaleratio=1, height=700,
                coloraxis_colorbar_title_text=selected_criteria_key
            )
            
            st.plotly_chart(fig, use_container_width=True)
            with st.expander("View Data Used for Plot"):
                st.dataframe(df_max_val[['Story', 'Column', 'Unique Name', 'X', 'Y', 'P', 'V2', 'V3', 'T', 'M2', 'M3', 'Output Case']])
        else:
            st.warning("No data found for the selected story.")
else:
    st.info("Please upload an Excel file (.xlsx) in the sidebar to begin.")

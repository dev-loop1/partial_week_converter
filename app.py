from flask import Flask, render_template, request, send_file, flash, redirect, url_for
import pandas as pd
from io import BytesIO
import os

# Initialize the Flask App
app = Flask(__name__)
app.secret_key = os.urandom(24) 

def disaggregate_dataframe(df: pd.DataFrame, date_column: str, value_column: str) -> pd.DataFrame:
    """
    Takes a DataFrame and disaggregates rows where the fiscal week spans two months.
    This version is corrected to robustly preserve all other columns and their order.
    """
    # --- 1. Validate and Prepare Data ---
    required_cols = {date_column, value_column}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"Input file is missing one or more required columns. Expected: {', '.join(required_cols)}")

    # Store original column order to use for the final output
    original_column_order = list(df.columns)
    df[date_column] = pd.to_datetime(df[date_column])
    
    # --- 2. Process Data ---
    output_rows = []
    
    for _, row in df.iterrows():
        original_row_data = row.to_dict()
        start_date = original_row_data[date_column]
        value = original_row_data[value_column]
        end_date = start_date + pd.Timedelta(days=6)
        
        if start_date.month == end_date.month:
            output_rows.append(original_row_data)
        else:
            days_in_first_month = (start_date.days_in_month - start_date.day) + 1
            days_in_second_month = 7 - days_in_first_month
            value_first_part = (value / 7) * days_in_first_month
            value_second_part = (value / 7) * days_in_second_month
            
            # First Partial Week Row (preserves all original data)
            new_row_1 = original_row_data.copy()
            new_row_1[value_column] = round(value_first_part, 2)
            output_rows.append(new_row_1)
            
            # Second Partial Week Row (preserves all original data)
            new_row_2 = original_row_data.copy()
            new_row_2[value_column] = round(value_second_part, 2)
            new_row_2[date_column] = end_date.replace(day=1)
            output_rows.append(new_row_2)

    if not output_rows:
        return pd.DataFrame()

    result_df = pd.DataFrame(output_rows)
    
    # --- 3. Final Formatting and Column Ordering ---
    # The dataframe is now built with all data, but the date column still has its original name.
    
    # First, format the date column before renaming it.
    result_df[date_column] = result_df[date_column].dt.strftime('%d-%b-%Y')
    
    # Now, create the list of final column names in the correct order.
    # We replace the original date column's name with 'Partial Week'.
    final_column_order = []
    for col_name in original_column_order:
        if col_name == date_column:
            final_column_order.append('Partial Week')
        else:
            final_column_order.append(col_name)

    # Rename the date column in the dataframe itself
    result_df.rename(columns={date_column: 'Partial Week'}, inplace=True)
    
    # Reorder the dataframe columns to match the desired final order.
    # This is the key step to ensure the output looks exactly like the input, but with the modified data.
    result_df = result_df[final_column_order]

    return result_df

@app.route('/')
def index():
    """Renders the main upload page."""
    return render_template('index.html')

@app.route('/process', methods=['POST'])
def process_file():
    """Handles the file upload and processing."""
    if 'file' not in request.files:
        flash('No file part in the request. Please select a file.', 'error')
        return redirect(url_for('index'))

    file = request.files['file']
    if file.filename == '':
        flash('No file selected. Please select a file to upload.', 'error')
        return redirect(url_for('index'))

    if not file.filename.endswith('.xlsx'):
        flash('Invalid file type. Please upload a .xlsx Excel file.', 'error')
        return redirect(url_for('index'))

    date_col = request.form.get('date_column')
    value_col = request.form.get('value_column')
    
    if not all([date_col, value_col]):
        flash('Both column name fields must be filled out.', 'error')
        return redirect(url_for('index'))

    try:
        input_df = pd.read_excel(file)
        output_df = disaggregate_dataframe(input_df, date_col, value_col)
        
        output_buffer = BytesIO()
        output_df.to_excel(output_buffer, index=False, sheet_name='Partial_Weeks')
        output_buffer.seek(0)

        return send_file(
            output_buffer,
            download_name=f"{os.path.splitext(file.filename)[0]}_partial_week_output.xlsx",
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        flash(f'An error occurred: {e}', 'error')
        return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0')

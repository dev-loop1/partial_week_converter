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
    """
    # --- 1. Validate and Prepare Data ---
    required_cols = {date_column, value_column}
    if not required_cols.issubset(df.columns):
        raise ValueError(f"Input file is missing one or more required columns. Expected: {', '.join(required_cols)}")

    original_column_order = list(df.columns)
    df[date_column] = pd.to_datetime(df[date_column])
    
    # --- 2. Process Data Row-by-Row to Preserve Order ---
    output_rows = []
    
    for _, row in df.iterrows():
        # Using to_dict() on each row ensures all original columns are preserved.
        original_row_data = row.to_dict()
        start_date = original_row_data[date_column]
        value = original_row_data[value_column]
        end_of_week = start_date + pd.Timedelta(days=6)
        
        # Use robust period comparison to check if the week needs to be split
        is_split = start_date.to_period('M') != end_of_week.to_period('M')
        
        if not is_split:
            # If not split, append the original row data directly.
            output_rows.append(original_row_data)
        else:
            # If split, perform the robust calculation and append the two new rows.
            end_of_month = start_date + pd.offsets.MonthEnd(0)
            end_of_first_part = min(end_of_week, end_of_month)
            
            days_in_first_part = (end_of_first_part - start_date).days + 1
            days_in_second_part = 7 - days_in_first_part
            
            # This is the proportional split logic based on number of days
            value_first_part = (value / 7) * days_in_first_part if days_in_first_part > 0 else 0
            value_second_part = value - round(value_first_part, 2) # More robust sum
            
            # First Partial Week Row
            new_row_1 = original_row_data.copy()
            new_row_1[value_column] = round(value_first_part, 2)
            output_rows.append(new_row_1)
            
            # Second Partial Week Row (if it exists)
            if days_in_second_part > 0:
                new_row_2 = original_row_data.copy()
                new_row_2[value_column] = round(value_second_part, 2)
                # The second part always starts on day 1 of the next month
                new_row_2[date_column] = end_of_week.replace(day=1, month=end_of_week.month, year=end_of_week.year)
                output_rows.append(new_row_2)

    # --- 3. Create Final DataFrame and Format ---
    result_df = pd.DataFrame(output_rows)
    
    # Ensure the date column is of datetime type before formatting
    result_df[date_column] = pd.to_datetime(result_df[date_column])
    result_df[date_column] = result_df[date_column].dt.strftime('%d-%b-%Y')
    
    final_column_order = [ 'Partial Week' if col == date_column else col for col in original_column_order ]
    result_df.rename(columns={date_column: 'Partial Week'}, inplace=True)
    
    # Reorder columns to match the original input file's structure
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

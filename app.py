from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import os
import re
import pandas as pd
from datetime import timedelta

app = Flask(__name__)
CORS(app)

# Function to get all image filenames in static/images folder
def get_image_filenames():
    images_folder = os.path.join(app.static_folder, 'images')
    image_files = [filename for filename in os.listdir(images_folder) if filename.endswith(('.jpg', '.png'))]
    return image_files

# Define the function to convert seconds to hrs:min:sec.milliseconds format
def convert_seconds_to_hms(seconds):
    td = timedelta(seconds=float(seconds))
    return str(td)

# Define the function to convert time to seconds
def time_to_seconds(time_str):
    time_str = str(time_str)  # Ensure time_str is a string
    parts = time_str.split(':')
    if len(parts) < 3:
        return 0  # Return 0 seconds if the time format is invalid
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return round(hours * 3600 + minutes * 60 + seconds)

# Define the function to process each text file
def process_text_file(file_path, keyword):
    data = []
    filename = os.path.splitext(os.path.basename(file_path))[0]  # Strip the .txt extension
    with open(file_path, 'r') as file:
        lines = file.readlines()

    if len(lines) < 4:
        return data  # Skip files that do not have enough lines

    video_url = lines[0].strip()[11:]  # The first line is the video URL, ignoring the first 11 characters

    show_title = filename  # Assume filename is the show title unless specified otherwise
    i = 2  # Start from the 3rd line (index 2)
    filename_added = False

    # Escape the keyword for regex and account for possible spaces around it
    escaped_keyword = re.escape(keyword)
    keyword_pattern = re.compile(r'\b' + escaped_keyword + r'\b', re.IGNORECASE)

    while i < len(lines):
        line = lines[i].strip()
        if '-->' in line:
            # Split timestamp into start_time and end_time
            timestamp_parts = line.strip().split('-->')
            if len(timestamp_parts) == 2:
                start_time = convert_seconds_to_hms(timestamp_parts[0].strip())
                end_time = convert_seconds_to_hms(timestamp_parts[1].strip())
            else:
                i += 2  # Skip this block if timestamp format is incorrect
                continue

            # Extract the spoken sentence from the next line
            if i + 1 < len(lines):
                spoken_sentence = lines[i + 1].strip()
            else:
                spoken_sentence = ""

            # Replace non-breaking spaces with regular spaces for matching
            normalized_sentence = spoken_sentence.replace('\u00A0', ' ')

            # Check if the keyword is in the spoken sentence using regex (case-insensitive)
            if keyword_pattern.search(normalized_sentence):
                if not filename_added:
                    data.append([show_title, start_time, end_time, spoken_sentence, video_url])
                    filename_added = True
                else:
                    data.append(['', start_time, end_time, spoken_sentence, video_url])

        i += 2  # Move to the next timestamp-transcript pair
    return data

# Define the function to process URLs to plain text for Excel
def process_urls_to_text(val):
    if val.startswith('http'):
        return val
    else:
        return f'https://{val}'

# Define the function to process files in batches
def process_files_in_batches(folder_path, keyword, batch_size=100):
    results = []
    text_files = [f for f in os.listdir(folder_path) if f.endswith('.txt')]
    total_files = len(text_files)
    for start in range(0, total_files, batch_size):
        end = min(start + batch_size, total_files)
        batch_files = text_files[start:end]
        for text_file in batch_files:
            file_path = os.path.join(folder_path, text_file)
            results.extend(process_text_file(file_path, keyword))
    return results

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/meme')
def show_meme_page():
    image_files = get_image_filenames()
    num_images = len(image_files)  # Get the number of images
    return render_template('meme.html', image_files=image_files, num_images=num_images)

@app.route('/submit', methods=['POST'])
def submit_text():
    data = request.get_json()
    keyword = data.get('text')
    selected_option = data.get('option')

    print(f"Received keyword from user: {keyword}")
    print(f"Selected option from user: {selected_option}")

    if selected_option == 'one':
        folder_path = os.path.join(os.path.dirname(__file__), 'transcripts_ar')
    elif selected_option == 'two':
        folder_path = os.path.join(os.path.dirname(__file__), 'transcripts_pt3')
    elif selected_option == 'three':
        folder_path = os.path.join(os.path.dirname(__file__), 'transcripts_ji')
    else:
        return jsonify({"message": "Invalid option selected", "table": ""}), 400

    all_data = process_files_in_batches(folder_path, keyword, batch_size=100)

    if all_data:
        df = pd.DataFrame(all_data, columns=['show_title', 'start_time', 'end_time', 'spoken_sentence', 'video_url'])
        print("DataFrames with keyword found:")
        df['start_time_seconds'] = df['start_time'].apply(time_to_seconds)
        df['video_url_with_timestamp'] = df.apply(lambda row: f"{row['video_url']}&t={row['start_time_seconds']}", axis=1)
        df.drop(columns=['video_url'], inplace=True)
        df['video_url_with_timestamp'] = df['video_url_with_timestamp'].apply(process_urls_to_text)
        output_dir = os.path.join(os.path.dirname(__file__), 'output')
        os.makedirs(output_dir, exist_ok=True)
        excel_file_path = os.path.join(output_dir, 'processed_table.xlsx')
        df.to_excel(excel_file_path, index=False, engine='openpyxl')

        def make_clickable(val):
            if val.startswith('http'):
                return f'<a href="{val}" target="_blank">{val}</a>'
            else:
                return val

        df['video_url_with_timestamp'] = df['video_url_with_timestamp'].apply(make_clickable)
        table_html = df.to_html(classes='table table-striped table-bordered', index=False, escape=False)
        print(df)
        rows_per_page = 100
        total_rows = len(df)
        total_pages = (total_rows + rows_per_page - 1) // rows_per_page

        return jsonify({
            "message": "Data processed successfully",
            "table": table_html,
            "download_url": f"/download/{os.path.basename(excel_file_path)}",
            "total_pages": total_pages,
            "rows_per_page": rows_per_page
        })
    else:
        return jsonify({"message": f"No lines containing the keyword '{keyword}' found in any text file.", "table": ""}), 200

@app.route('/download/<filename>')
def download_file(filename):
    output_dir = os.path.join(os.path.dirname(__file__), 'output')
    file_path = os.path.join(output_dir, filename)
    if os.path.isfile(file_path):
        return send_file(file_path, as_attachment=True)
    else:
        return jsonify({"error": "File not found."}), 404

if __name__ == '__main__':
    app.run(debug=True)

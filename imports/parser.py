import csv
import io

def parse_csv(file_obj) -> list[dict]:
    """
    Reads a CSV file dynamically into a list of dictionaries.

    Why: Avoids assuming any specific column schema, making the framework extensible.
    Preserves the original 1-based row line index of the source CSV file
    under the key '_row_index' to maintain strict audit traceability.

    Parameters:
        file_obj: A file-like object or bytes, representing the uploaded CSV file.

    Returns:
        list of dict: A list where each element represents a row from the CSV file
        with its original columns plus a '_row_index' field.
    """
    # Why: Handle file decoding if content is in bytes (standard for Django UploadedFile)
    if hasattr(file_obj, 'read'):
        content = file_obj.read()
        if isinstance(content, bytes):
            text = content.decode('utf-8-sig')  # utf-8-sig automatically strips Byte Order Mark (BOM)
        else:
            text = content
        # Why: Reset file pointer so other readers or operations can access it if needed
        if hasattr(file_obj, 'seek'):
            file_obj.seek(0)
        f = io.StringIO(text)
    else:
        # Fallback to opening file path if it's a string path
        f = open(file_obj, mode='r', encoding='utf-8-sig')

    reader = csv.DictReader(f)
    rows = []
    
    # Why: Start numbering at 2 since header is line 1, so the first data row is line 2
    for idx, row in enumerate(reader, start=2):
        row_dict = dict(row)
        # Why: Attach raw line number reference directly to the data dictionary for traceability
        row_dict['_row_index'] = idx
        rows.append(row_dict)

    return rows

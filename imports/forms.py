from django import forms

class CSVUploadForm(forms.Form):
    """
    Form to upload a CSV file.

    Why: Captures the file payload for the parsing pipeline, restricting uploads
    to CSV format.
    """
    csv_file = forms.FileField(
        widget=forms.ClearableFileInput(attrs={
            'class': 'form-control',
            'accept': '.csv',
            'id': 'id_csv_file'
        }),
        label="CSV File",
        help_text="Please select a valid CSV file containing expense data."
    )

from django.urls import path
from .views import ImportUploadView, ImportReviewView

urlpatterns = [
    # Why: Routes to the CSV uploading page scoped to a specific group.
    path(
        'groups/<int:group_id>/import/',
        ImportUploadView.as_view(),
        name='import_upload'
    ),

    # Why: Routes to the anomaly review page (Meera's approval gate) for a batch.
    path(
        'imports/batch/<int:batch_id>/review/',
        ImportReviewView.as_view(),
        name='import_review'
    ),
]

from django.urls import path

from .views import complete_upload, initiate_upload

urlpatterns = [
    path("initiate-upload/", initiate_upload, name="asset-initiate-upload"),
    path("<uuid:asset_id>/complete/", complete_upload, name="asset-complete-upload"),
]

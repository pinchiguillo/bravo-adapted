from django.urls import path

from .views import CategoryServiceViewSet

category_service_list = CategoryServiceViewSet.as_view({"get": "list"})

urlpatterns = [
    path(
        "<uuid:category_uuid>/services/",
        category_service_list,
        name="category-service-list",
    ),
]

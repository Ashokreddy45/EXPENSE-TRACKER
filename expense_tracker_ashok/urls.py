# urls.py in the main project directory (expense_tracker_ashok)

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', include('home.urls')),  # Include URLs from the home app
]

from django.urls import path

from observation_portal.observations.views import ObservationListView, ObservationDetailView

app_name = 'observations'

urlpatterns = [
    path('', ObservationListView.as_view(), name='observation-list'),
    path('<int:pk>/', ObservationDetailView.as_view(), name='observation-detail'),
]

from rest_framework.routers import DefaultRouter
from .views import CandidateViewSet, ApplicationViewSet

router = DefaultRouter()
router.register(r'candidates',   CandidateViewSet,   basename='candidate')
router.register(r'applications', ApplicationViewSet, basename='application')

urlpatterns = router.urls
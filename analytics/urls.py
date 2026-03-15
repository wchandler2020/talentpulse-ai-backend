from rest_framework.routers import DefaultRouter
from .views import PipelineEventViewSet, AIUsageLogViewSet, DashboardViewSet

router = DefaultRouter()
router.register(r'pipeline-events', PipelineEventViewSet, basename='pipeline-event')
router.register(r'ai-usage', AIUsageLogViewSet, basename='ai-usage')
router.register(r'dashboard', DashboardViewSet, basename='dashboard')

urlpatterns = router.urls
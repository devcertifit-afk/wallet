"""
URL configuration for wallet_platform project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from passes.views import (
    landing_page, CompanyViewSet, PassTemplateViewSet, 
    PassInstanceViewSet, PassAnalyticsViewSet,
    dashboard_register, dashboard_login, dashboard_logout, dashboard_index,
    dashboard_templates, dashboard_instances, dashboard_employees
)

router = DefaultRouter()
router.register(r'companies', CompanyViewSet, basename='company')
router.register(r'templates', PassTemplateViewSet, basename='template')
router.register(r'instances', PassInstanceViewSet, basename='instance')
router.register(r'analytics', PassAnalyticsViewSet, basename='analytics')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include(router.urls)),
    path('', landing_page, name='landing'),
    
    # Merchant Dashboard routes
    path('register/', dashboard_register, name='register'),
    path('login/', dashboard_login, name='login'),
    path('logout/', dashboard_logout, name='dashboard-logout'),
    path('dashboard/', dashboard_index, name='dashboard-index'),
    path('dashboard/templates/', dashboard_templates, name='dashboard-templates'),
    path('dashboard/instances/', dashboard_instances, name='dashboard-instances'),
    path('dashboard/employees/', dashboard_employees, name='dashboard-employees'),

    # Ticketing routes
    path('', include('ticketing.urls')),
]



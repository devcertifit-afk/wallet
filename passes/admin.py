from django.contrib import admin
from .models import Company, Employee, PassTemplate, PassInstance, PassAnalytics

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)

@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('user', 'company', 'role', 'created_at')
    list_filter = ('role', 'company')
    search_fields = ('user__username', 'company__name')

@admin.register(PassTemplate)
class PassTemplateAdmin(admin.ModelAdmin):
    list_display = ('title', 'company', 'pass_type', 'created_at')
    list_filter = ('pass_type', 'company')
    search_fields = ('title', 'company__name')

@admin.register(PassInstance)
class PassInstanceAdmin(admin.ModelAdmin):
    list_display = ('customer_name', 'customer_email', 'template', 'balance', 'is_active', 'created_at')
    list_filter = ('is_active', 'template__pass_type', 'template__company')
    search_fields = ('customer_name', 'customer_email', 'serial_number')
    readonly_fields = ('serial_number',)

@admin.register(PassAnalytics)
class PassAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('company', 'event_type', 'value_changed', 'timestamp')
    list_filter = ('event_type', 'company')
    search_fields = ('company__name', 'pass_instance__customer_name')
    readonly_fields = ('timestamp',)

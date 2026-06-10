from rest_framework import serializers
from .models import Company, Employee, PassTemplate, PassInstance, PassAnalytics

class CompanySerializer(serializers.ModelSerializer):
    class Meta:
        model = Company
        fields = ['id', 'name', 'slug', 'created_at', 'updated_at']

class PassTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PassTemplate
        fields = [
            'id', 'company', 'pass_type', 'title', 'description', 
            'logo', 'background_color', 'foreground_color', 'label_color',
            'apple_pass_type_id', 'google_class_id', 'sku', 'custom_metadata', 
            'default_data', 'created_at', 'updated_at'
        ]

class PassInstanceSerializer(serializers.ModelSerializer):
    pass_type = serializers.CharField(source='template.pass_type', read_only=True)
    sku = serializers.CharField(source='template.sku', read_only=True)

    class Meta:
        model = PassInstance
        fields = [
            'id', 'template', 'pass_type', 'sku', 'serial_number', 'google_object_id',
            'customer_name', 'customer_email', 'balance', 'pass_data', 'is_active',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['serial_number', 'google_object_id']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.template.pass_type == 'LOYALTY':
            representation['balance'] = int(instance.balance)
        return representation

class PassAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = PassAnalytics
        fields = ['id', 'company', 'pass_instance', 'event_type', 'value_changed', 'timestamp']

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        if instance.pass_instance and instance.pass_instance.template.pass_type == 'LOYALTY':
            representation['value_changed'] = int(instance.value_changed)
        return representation

"""Member serializers."""
from rest_framework import serializers

from apps.members.models import Member


class MemberSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(source="user.email", read_only=True, default=None)
    is_placeholder = serializers.BooleanField(read_only=True)

    class Meta:
        model = Member
        fields = ["id", "group", "display_name", "role", "is_active", "email", "is_placeholder"]
        read_only_fields = ["group", "is_active"]


class AddMemberSerializer(serializers.Serializer):
    """Add a member either by existing user email or as a placeholder name."""

    email = serializers.EmailField(required=False)
    display_name = serializers.CharField(max_length=150, required=False)

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("display_name"):
            raise serializers.ValidationError("Provide an email or a display_name.")
        return attrs

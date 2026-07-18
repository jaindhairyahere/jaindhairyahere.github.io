"""Group serializers."""
from rest_framework import serializers

from apps.groups.models import Group, GroupKind
from apps.members.serializers import MemberSerializer


class GroupSerializer(serializers.ModelSerializer):
    members = MemberSerializer(many=True, read_only=True)
    is_friend = serializers.BooleanField(read_only=True)

    class Meta:
        model = Group
        fields = [
            "id", "name", "kind", "base_currency", "simplify_enabled",
            "is_friend", "members", "created_at",
        ]
        read_only_fields = ["kind", "is_friend", "members", "created_at"]


class CreateGroupSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    base_currency = serializers.ChoiceField(choices=["INR", "USD", "EUR"], default="INR")
    simplify_enabled = serializers.BooleanField(default=True)


class CreateFriendGroupSerializer(serializers.Serializer):
    email = serializers.EmailField(required=False)
    other_name = serializers.CharField(max_length=150, required=False)
    base_currency = serializers.ChoiceField(choices=["INR", "USD", "EUR"], default="INR")

    def validate(self, attrs):
        if not attrs.get("email") and not attrs.get("other_name"):
            raise serializers.ValidationError("Provide an email or other_name.")
        return attrs

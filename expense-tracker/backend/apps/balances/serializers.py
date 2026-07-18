from rest_framework import serializers

from apps.balances.models import Settlement


class SettlementSerializer(serializers.ModelSerializer):
    from_name = serializers.CharField(source="from_member.display_name", read_only=True)
    to_name = serializers.CharField(source="to_member.display_name", read_only=True)

    class Meta:
        model = Settlement
        fields = [
            "id", "group", "from_member", "to_member", "from_name", "to_name",
            "amount", "currency", "date", "note", "created_at",
        ]
        read_only_fields = ["created_at"]

    def validate(self, attrs):
        group = attrs.get("group")
        for key in ("from_member", "to_member"):
            member = attrs.get(key)
            if member and member.group_id != group.id:
                raise serializers.ValidationError(f"{key} must belong to the group.")
        if attrs.get("from_member") == attrs.get("to_member"):
            raise serializers.ValidationError("A settlement needs two different members.")
        return attrs
